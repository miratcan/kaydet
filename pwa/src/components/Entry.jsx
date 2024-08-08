
function Tag({_key, val}) {
  return <span class="tag {key}">{_key}: {val}</span>
}

export function Entry({ data }) {
  console.log(data)
  return (
    <div class="entry">
      { data.title && <h3>{data.title}</h3>}
      <div class="tags">
        {data.tags && Object.entries(data.tags).map(([_key, val]) => {
          return <Tag _key={_key} val={val} />
        })}
      </div>
      <div class="content">{data.content.map((line) => <p>{line}</p>)}</div>
    </div>
  )
}
