// Entry Packet — binary serialize/deserialize
//
// Spec: docs/spec/v1/entry-packet.md
//
// Format:
//   [4]  magic: 0x4B 0x59 0x44 0x54 ("KYDT")
//   [1]  version: 0x01
//   [1]  flags: HAS_ATTACHMENTS(0) | IS_ENCRYPTED(1) | IS_COMPRESSED(2)
//   [4]  id_len
//   [n]  id (UTF-8 NFC)
//   [2]  ts_len
//   [n]  timestamp
//   [4]  text_len
//   [n]  text
//   [2]  attachment_count
//   per attachment:
//     [2]  name_len
//     [n]  name
//     [8]  data_len
//     [n]  data
//   [4]  CRC32
//
// Python karşılığı:
//   def serialize(entry, attachments):
//       buf = bytearray()
//       buf += b'KYDT'
//       buf += bytes([0x01, flags])
//       buf += struct.pack('>I', len(entry.id)) + entry.id.encode()
//       ...
//       buf += struct.pack('>I', crc32(buf))
//       return bytes(buf)

use crc32fast::Hasher;
use std::collections::HashMap;

use crate::Entry;

const MAGIC: &[u8; 4] = b"KYDT";
const VERSION: u8 = 0x01;

const FLAG_HAS_ATTACHMENTS: u8 = 0x01;
const FLAG_IS_ENCRYPTED: u8 = 0x02;
const FLAG_IS_COMPRESSED: u8 = 0x04;

#[derive(Debug)]
pub enum PacketError {
    BadMagic,
    BadVersion(u8),
    BadFlags(u8),
    BadChecksum,
    UnexpectedEof,
    InvalidUtf8(String),
}

impl std::fmt::Display for PacketError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PacketError::BadMagic => write!(f, "bad magic bytes"),
            PacketError::BadVersion(v) => write!(f, "unsupported version: {}", v),
            PacketError::BadFlags(b) => write!(f, "reserved flag bits set: {:08b}", b),
            PacketError::BadChecksum => write!(f, "CRC32 mismatch"),
            PacketError::UnexpectedEof => write!(f, "unexpected end of data"),
            PacketError::InvalidUtf8(s) => write!(f, "invalid UTF-8: {}", s),
        }
    }
}

// ---------------------------------------------------------------------------
// Serialize
// ---------------------------------------------------------------------------

pub fn serialize(entry: &Entry, attachments: &HashMap<String, Vec<u8>>) -> Vec<u8> {
    let mut buf: Vec<u8> = Vec::new();

    // flags
    let mut flags: u8 = 0;
    if !attachments.is_empty() {
        flags |= FLAG_HAS_ATTACHMENTS;
    }

    // header
    buf.extend_from_slice(MAGIC);
    buf.push(VERSION);
    buf.push(flags);

    // entry block
    write_str(&mut buf, &entry.entry_id, 4);
    write_str(&mut buf, &entry.timestamp, 2);
    write_str(&mut buf, &entry.text, 4);

    // attachments
    buf.extend_from_slice(&(attachments.len() as u16).to_be_bytes());
    // sırala — deterministik output için
    let mut att_names: Vec<&String> = attachments.keys().collect();
    att_names.sort();
    for name in att_names {
        let data = &attachments[name];
        write_str(&mut buf, name, 2);
        buf.extend_from_slice(&(data.len() as u64).to_be_bytes());
        buf.extend_from_slice(data);
    }

    // CRC32
    let checksum = crc32(&buf);
    buf.extend_from_slice(&checksum.to_be_bytes());

    buf
}

// ---------------------------------------------------------------------------
// Deserialize
// ---------------------------------------------------------------------------

pub struct PacketEntry {
    pub entry: Entry,
    pub attachments: HashMap<String, Vec<u8>>,
}

pub fn deserialize(data: &[u8]) -> Result<PacketEntry, PacketError> {
    let mut r = Reader::new(data);

    // CRC32 doğrula — son 4 byte checksum, geri kalanı veri
    if data.len() < 4 {
        return Err(PacketError::UnexpectedEof);
    }
    let payload = &data[..data.len() - 4];
    let stored_crc = u32::from_be_bytes(
        data[data.len() - 4..].try_into().unwrap()
    );
    if crc32(payload) != stored_crc {
        return Err(PacketError::BadChecksum);
    }

    // magic
    let magic = r.read_bytes(4)?;
    if magic != MAGIC {
        return Err(PacketError::BadMagic);
    }

    // version
    let version = r.read_u8()?;
    if version != VERSION {
        return Err(PacketError::BadVersion(version));
    }

    // flags
    let flags = r.read_u8()?;
    if flags & 0xF8 != 0 {
        // reserved bits 3-7 set
        return Err(PacketError::BadFlags(flags));
    }

    // entry block
    let entry_id = r.read_str(4)?;
    let timestamp = r.read_str(2)?;
    let text = r.read_str(4)?;

    // attachments
    let att_count = r.read_u16()? as usize;
    let mut attachments: HashMap<String, Vec<u8>> = HashMap::new();
    for _ in 0..att_count {
        let name = r.read_str(2)?;
        let data_len = r.read_u64()? as usize;
        let data = r.read_bytes(data_len)?.to_vec();
        attachments.insert(name, data);
    }

    // Entry oluştur — originator_id ve hop_path packet'ta yok,
    // bunlar sync katmanının sorumluluğu
    let mut entry = Entry::from_text(&text);
    entry.entry_id = entry_id;
    entry.timestamp = timestamp;

    Ok(PacketEntry { entry, attachments })
}

// ---------------------------------------------------------------------------
// Reader — byte slice üzerinde cursor
// ---------------------------------------------------------------------------

struct Reader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn new(data: &'a [u8]) -> Reader<'a> {
        Reader { data, pos: 0 }
    }

    fn read_bytes(&mut self, n: usize) -> Result<&'a [u8], PacketError> {
        if self.pos + n > self.data.len() {
            return Err(PacketError::UnexpectedEof);
        }
        let slice = &self.data[self.pos..self.pos + n];
        self.pos += n;
        Ok(slice)
    }

    fn read_u8(&mut self) -> Result<u8, PacketError> {
        Ok(self.read_bytes(1)?[0])
    }

    fn read_u16(&mut self) -> Result<u16, PacketError> {
        let b = self.read_bytes(2)?;
        Ok(u16::from_be_bytes(b.try_into().unwrap()))
    }

    fn read_u64(&mut self) -> Result<u64, PacketError> {
        let b = self.read_bytes(8)?;
        Ok(u64::from_be_bytes(b.try_into().unwrap()))
    }

    fn read_str(&mut self, len_bytes: usize) -> Result<String, PacketError> {
        let len = match len_bytes {
            2 => self.read_u16()? as usize,
            4 => {
                let b = self.read_bytes(4)?;
                u32::from_be_bytes(b.try_into().unwrap()) as usize
            }
            _ => unreachable!(),
        };
        let bytes = self.read_bytes(len)?;
        String::from_utf8(bytes.to_vec())
            .map_err(|e| PacketError::InvalidUtf8(e.to_string()))
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn write_str(buf: &mut Vec<u8>, s: &str, len_size: usize) {
    let bytes = s.as_bytes();
    match len_size {
        2 => buf.extend_from_slice(&(bytes.len() as u16).to_be_bytes()),
        4 => buf.extend_from_slice(&(bytes.len() as u32).to_be_bytes()),
        _ => unreachable!(),
    }
    buf.extend_from_slice(bytes);
}

fn crc32(data: &[u8]) -> u32 {
    let mut h = Hasher::new();
    h.update(data);
    h.finalize()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Entry;

    fn make_entry(text: &str) -> Entry {
        let mut e = Entry::from_text(text);
        e.entry_id = "test-id-123".to_string();
        e.timestamp = "14:25".to_string();
        e
    }

    #[test]
    fn test_roundtrip_no_attachments() {
        let entry = make_entry("yolda not aldım #mirat");
        let packed = serialize(&entry, &HashMap::new());
        let result = deserialize(&packed).unwrap();
        assert_eq!(result.entry.entry_id, "test-id-123");
        assert_eq!(result.entry.timestamp, "14:25");
        assert_eq!(result.entry.text, "yolda not aldım #mirat");
        assert!(result.attachments.is_empty());
    }

    #[test]
    fn test_roundtrip_with_attachment() {
        let entry = make_entry("fotoğraf #mirat attachment:d1_photo.jpg");
        let mut attachments = HashMap::new();
        attachments.insert("d1_photo.jpg".to_string(), b"fake jpeg data".to_vec());

        let packed = serialize(&entry, &attachments);
        let result = deserialize(&packed).unwrap();

        assert_eq!(result.entry.text, "fotoğraf #mirat attachment:d1_photo.jpg");
        assert_eq!(
            result.attachments.get("d1_photo.jpg").unwrap(),
            b"fake jpeg data"
        );
    }

    #[test]
    fn test_bad_magic_rejected() {
        let entry = make_entry("test");
        let mut packed = serialize(&entry, &HashMap::new());
        packed[0] = 0xFF; // magic boz
        // CRC da bozulacak ama önce magic kontrolü
        assert!(matches!(
            deserialize(&packed),
            Err(PacketError::BadChecksum) | Err(PacketError::BadMagic)
        ));
    }

    #[test]
    fn test_checksum_mismatch() {
        let entry = make_entry("test");
        let mut packed = serialize(&entry, &HashMap::new());
        let last = packed.len() - 1;
        packed[last] ^= 0xFF; // checksum boz
        assert!(matches!(deserialize(&packed), Err(PacketError::BadChecksum)));
    }

    #[test]
    fn test_turkish_unicode() {
        let entry = make_entry("Türkçe metin: şğüöçı #test");
        let packed = serialize(&entry, &HashMap::new());
        let result = deserialize(&packed).unwrap();
        assert_eq!(result.entry.text, "Türkçe metin: şğüöçı #test");
    }
}
