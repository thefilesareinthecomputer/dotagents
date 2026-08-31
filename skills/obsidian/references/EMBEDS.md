# Embeds Reference

The `!` prefix on a wikilink **embeds** (transcludes) the target instead of linking to it.
Embeds are live, they update when the source changes.

## Embed notes
```
![[Note Name]]
![[Note Name#Heading]]
![[Note Name#^block-id]]
```

## Embed images (with sizing)
```
![[image.png]]
![[image.png|300]]        # width 300px
![[image.png|640x480]]    # width x height
```

## External images
```
![Alt text](https://example.com/image.png)
![Alt text|300](https://example.com/image.png)
```

## Embed audio / video
```
![[audio.mp3]]
![[clip.mp4]]
```

## Embed PDF
```
![[document.pdf]]
![[document.pdf#page=3]]
![[document.pdf#height=400]]
```

## Embed Bases (native database, 1.9+)
```
![[BaseFile.base]]
![[BaseFile.base#View Name]]
```

## Embed a list / block
Assign a block ID to the block, then embed it:
```
- Item 1
- Item 2
^list-id

![[Note#^list-id]]
```

## Embed search / query results
~~~
```query
tag:#project line:(done)
```
~~~

## The pipe-collision gotcha
The single `|` slot is overloaded: it means **alias** in `[[Note|Alias]]` but **size** in
`![[image.png|300]]`. There is **no native way to set both alt text and size** in one embed.
Workarounds:
- HTML: `<img src="path" width="300" alt="...">`
- Markdown-link form: `![alt|300](path)`
- Image Caption plugin: `![[img.png|50x50 "caption"]]`

Note: `|size` reliability varies by theme and can differ between Live Preview and Reading view.
