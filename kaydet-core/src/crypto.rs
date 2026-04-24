// crypto.rs — AES-256-GCM encryption with scrypt key derivation
//
// Binary format (compatible with Python's secrets.py):
//   salt (16 bytes) + nonce (12 bytes) + ciphertext+tag (n+16 bytes)
//
// KDF: scrypt(n=2^16, r=8, p=1) — OWASP interactive recommendation
// Cipher: AES-256-GCM

use aes_gcm::{
    aead::{Aead, KeyInit, OsRng},
    Aes256Gcm, Nonce,
};
use aes_gcm::aead::rand_core::RngCore;
use scrypt::{scrypt, Params};

#[derive(Debug)]
pub enum CryptoError {
    EncryptFailed(String),
    DecryptFailed(String),
    InvalidData(String),
}

impl std::fmt::Display for CryptoError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CryptoError::EncryptFailed(s) => write!(f, "encrypt failed: {}", s),
            CryptoError::DecryptFailed(s) => write!(f, "decrypt failed: {}", s),
            CryptoError::InvalidData(s) => write!(f, "invalid data: {}", s),
        }
    }
}

pub type CryptoResult<T> = Result<T, CryptoError>;

fn derive_key(password: &str, salt: &[u8]) -> CryptoResult<[u8; 32]> {
    // scrypt params: n=2^16, r=8, p=1 — matches Python's secrets.py
    let params = Params::new(16, 8, 1, 32)
        .map_err(|e| CryptoError::EncryptFailed(e.to_string()))?;
    let mut key = [0u8; 32];
    scrypt(password.as_bytes(), salt, &params, &mut key)
        .map_err(|e| CryptoError::EncryptFailed(e.to_string()))?;
    Ok(key)
}

/// Encrypt plaintext with AES-256-GCM, key derived via scrypt.
/// Returns: salt (16) + nonce (12) + ciphertext+tag
pub fn encrypt_secret(plaintext: &str, password: &str) -> CryptoResult<Vec<u8>> {
    let mut salt = [0u8; 16];
    OsRng.fill_bytes(&mut salt);

    let key_bytes = derive_key(password, &salt)?;
    let cipher = Aes256Gcm::new_from_slice(&key_bytes)
        .map_err(|e| CryptoError::EncryptFailed(e.to_string()))?;

    let mut nonce_bytes = [0u8; 12];
    OsRng.fill_bytes(&mut nonce_bytes);
    let nonce = Nonce::from_slice(&nonce_bytes);

    let ciphertext = cipher
        .encrypt(nonce, plaintext.as_bytes())
        .map_err(|e| CryptoError::EncryptFailed(e.to_string()))?;

    let mut result = Vec::with_capacity(16 + 12 + ciphertext.len());
    result.extend_from_slice(&salt);
    result.extend_from_slice(&nonce_bytes);
    result.extend_from_slice(&ciphertext);
    Ok(result)
}

/// Decrypt data produced by encrypt_secret.
pub fn decrypt_secret(encrypted: &[u8], password: &str) -> CryptoResult<String> {
    if encrypted.len() < 28 {
        return Err(CryptoError::InvalidData(
            format!("payload too short: {} bytes", encrypted.len())
        ));
    }

    let salt = &encrypted[..16];
    let nonce_bytes = &encrypted[16..28];
    let ciphertext = &encrypted[28..];

    let key_bytes = derive_key(password, salt)?;
    let cipher = Aes256Gcm::new_from_slice(&key_bytes)
        .map_err(|e| CryptoError::DecryptFailed(e.to_string()))?;

    let nonce = Nonce::from_slice(nonce_bytes);
    let plaintext = cipher
        .decrypt(nonce, ciphertext)
        .map_err(|_| CryptoError::DecryptFailed("authentication failed".to_string()))?;

    String::from_utf8(plaintext)
        .map_err(|e| CryptoError::DecryptFailed(e.to_string()))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encrypt_decrypt_roundtrip() {
        let plaintext = "gizli mesaj";
        let password = "test-password-123";
        let encrypted = encrypt_secret(plaintext, password).unwrap();
        let decrypted = decrypt_secret(&encrypted, password).unwrap();
        assert_eq!(decrypted, plaintext);
    }

    #[test]
    fn test_encrypt_produces_different_ciphertexts() {
        let plaintext = "aynı metin";
        let password = "aynı şifre";
        let enc1 = encrypt_secret(plaintext, password).unwrap();
        let enc2 = encrypt_secret(plaintext, password).unwrap();
        // random salt + nonce → farklı çıktı
        assert_ne!(enc1, enc2);
    }

    #[test]
    fn test_wrong_password_fails() {
        let encrypted = encrypt_secret("secret", "doğru-şifre").unwrap();
        assert!(decrypt_secret(&encrypted, "yanlış-şifre").is_err());
    }

    #[test]
    fn test_turkish_unicode() {
        let plaintext = "Melis çok güzel büyüdü 🐧";
        let password = "şifreyihatırlıyorum";
        let encrypted = encrypt_secret(plaintext, password).unwrap();
        let decrypted = decrypt_secret(&encrypted, password).unwrap();
        assert_eq!(decrypted, plaintext);
    }

    #[test]
    fn test_truncated_payload_error() {
        assert!(decrypt_secret(&[0u8; 10], "pass").is_err());
    }
}
