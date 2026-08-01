// Hop3 technical reports — shared style.
//
// Adapted from the Fediversity companion-paper style, itself adapted from the
// Hop3 experience-report bundle. Applied by build/<name>/report.typ, which
// build.py generates; the body is md2typst output with its front matter
// stripped, so this file owns every visual decision in the document.
//
// One style for every TR on purpose: they are a numbered series, and a reader
// who has seen one should recognise the next.

// ============================================================================
// Palette — Hop3 slate, kept in family with the experience reports and the
// companion paper: these are all Hop3 publications and should read as one set.
// ============================================================================

#let accent      = rgb("#1f4e5f")
#let accent-soft = rgb("#eef3f5")
#let rule-gray   = luma(210)
#let muted       = luma(95)
#let ink         = rgb("#0d1117")
#let code-bg     = luma(248)

// Every family listed must exist, because Typst warns once per unknown family
// on every compile even when an earlier entry in the list already matched.
// Each list ends with something ubiquitous: Libertinus Serif and New Computer
// Modern ship with Typst itself, and DejaVu Sans Mono is on essentially every
// Linux box. Check with `typst fonts` before adding to these.
#let body-font    = ("Charter", "IBM Plex Serif", "Source Serif Pro", "Libertinus Serif", "New Computer Modern")
#let display-font = ("Inter", "IBM Plex Sans", "Source Sans Pro", "Helvetica Neue")
#let mono-font    = ("JetBrains Mono", "IBM Plex Mono", "DejaVu Sans Mono")

#let org-name = "Abilian — Hop3"
#let org-url  = "hop3.cloud"

#let report(
  title: "",
  subtitle: none,
  kicker: none,
  author: none,
  date: none,
  status: none,
  // Remaining `**Key:** value` front-matter pairs, as ((key, value), ...).
  // Rendered under the cover rule so that nothing in the source's front matter
  // is silently dropped on the way into the PDF.
  meta: (),
  // Left-hand running header on pages 2+. The report's short id, e.g. "TR-01".
  running: none,
  paper: "a4",
  body,
) = {
  set document(title: title, author: if author != none { author } else { org-name })

  set page(
    paper: paper,
    margin: (top: 2.4cm, bottom: 2.2cm, left: 2.5cm, right: 2.5cm),
    numbering: "1",

    // Pages 2+: report id left, current section right, so a reader who opens
    // the PDF in the middle knows where they are.
    header: context {
      if counter(page).get().first() > 1 {
        // Headings that start on this page count as current. `before(here())`
        // would not include them, because the header is laid out above the
        // body and would name the previous section on every section opening.
        let p = here().page()
        let secs = query(heading.where(level: 2)).filter(h => h.location().page() <= p)
        // Render the heading body rather than flattening it to a string: the
        // flattener drops the space elements between words.
        let label = if secs.len() > 0 { secs.last().body } else { [] }
        grid(
          columns: (auto, 1fr),
          align: (left + horizon, right + horizon),
          text(size: 8pt, fill: muted, font: display-font, tracking: 0.4pt)[
            #if running != none { running } else { org-name }
          ],
          text(size: 8pt, fill: muted, font: display-font)[#label],
        )
        v(0.2em)
        line(length: 100%, stroke: 0.5pt + rule-gray)
      }
    },

    footer: context {
      set text(8.5pt, fill: muted, font: display-font)
      line(length: 100%, stroke: 0.5pt + rule-gray)
      v(0.4em)
      grid(
        columns: (1fr, auto, 1fr),
        align(left)[#org-name],
        align(center)[#counter(page).display("1 / 1", both: true)],
        align(right)[#org-url],
      )
    },
  )

  set text(font: body-font, size: 10pt, hyphenate: true)
  set par(leading: 0.50em, spacing: 1.35em, justify: true, first-line-indent: 0pt)
  set raw(theme: none)
  show raw: set text(font: mono-font, size: 8.5pt)

  // --- cover ---------------------------------------------------------------
  if kicker != none and kicker != "" {
    block(above: 3.0cm, below: 0.8em)[
      #set text(font: display-font, weight: 600, size: 8.5pt, fill: accent, tracking: 1.2pt)
      #upper(kicker)
    ]
  }
  block(above: if kicker != none and kicker != "" { 0em } else { 3.2cm }, below: 1.1em)[
    #set text(font: display-font, weight: 700, size: 24pt, fill: ink, hyphenate: false)
    #set par(leading: 0.5em, justify: false)
    #title
  ]
  if subtitle != none and subtitle != "" {
    block(below: 1.2em)[
      #set text(font: display-font, weight: 400, size: 13pt, fill: luma(70), hyphenate: false)
      #set par(leading: 0.6em, justify: false)
      #subtitle
    ]
  }
  {
    let parts = ()
    if author != none and author != "" { parts.push(author) }
    if date != none and date != "" { parts.push(date) }
    if status != none and status != "" { parts.push(upper(status)) }
    if parts.len() > 0 {
      block(below: 1.3em)[
        #set text(size: 9pt, font: display-font, fill: muted, tracking: 0.6pt)
        #parts.join(text(fill: accent)[ · ])
      ]
    }
  }
  line(length: 100%, stroke: 0.6pt + accent)

  // Everything else the front matter carried: contact, project, licence, and
  // the long prose Status line. Dropping these would lose real information
  // between the markdown and the PDF.
  if meta.len() > 0 {
    v(1.0em)
    block(width: 100%)[
      #set text(size: 8.5pt, font: display-font, fill: luma(60))
      #set par(justify: false, leading: 0.55em)
      #grid(
        columns: (auto, 1fr),
        column-gutter: 1.0em,
        row-gutter: 0.55em,
        ..meta.map(((k, v)) => (
          text(weight: 600, fill: accent)[#k],
          [#v],
        )).flatten()
      )
    ]
  }

  v(1.8em)
  block[
    #set text(font: display-font, weight: 600, size: 11pt, fill: accent)
    Contents
  ]
  v(0.5em)
  // Sections arrive as level 2 (see the heading rules below), so depth 2 lists
  // the numbered sections and nothing finer. Depth 3 would add some fifty
  // subsections and turn a contents block into three pages.
  outline(title: none, depth: 2, indent: 1.2em)

  pagebreak(weak: true)

  // --- headings ------------------------------------------------------------
  // md2typst maps markdown H1 to `=`, H2 to `==`, H3 to `===`. build.py strips
  // the H1 (it becomes the cover title), so the numbered sections arrive here
  // as level 2 and their subsections as level 3. Targeting level 1 would match
  // nothing and silently style every section as a subsection.
  show heading.where(level: 2): it => block(above: 2.0em, below: 0.8em)[
    #set text(font: display-font, weight: 700, size: 16pt, fill: ink, hyphenate: false)
    #set par(leading: 0.5em, justify: false)
    #show link: l => l.body
    #it.body
  ]

  show heading.where(level: 3): it => block(above: 1.6em, below: 0.7em)[
    #set text(font: display-font, weight: 700, size: 12pt, fill: accent, hyphenate: false)
    #show link: l => l.body
    #set par(justify: false, leading: 0.55em)
    #it.body
  ]

  show heading.where(level: 4): it => block(above: 1.4em, below: 0.6em)[
    #set text(font: display-font, weight: 600, size: 10.5pt, fill: luma(50), hyphenate: false)
    #show link: l => l.body
    #set par(justify: false, leading: 0.5em)
    #it.body
  ]

  show heading.where(level: 5): it => block(above: 1.2em, below: 0.5em)[
    #set text(font: display-font, weight: 500, size: 10pt, fill: luma(80), style: "italic", hyphenate: false)
    #show link: l => l.body
    #set par(justify: false)
    #it.body
  ]

  // Bold carries the lead of a paragraph throughout these reports; give it
  // weight and ink rather than colour, which would fight the accent headings.
  show strong: it => text(weight: 700, fill: ink)[#it.body]

  set list(indent: 0.6em, body-indent: 0.6em)
  set enum(
    indent: 0.4em,
    body-indent: 0.5em,
    numbering: n => text(fill: accent, weight: 600)[#n.],
  )

  show quote.where(block: true): it => block(
    width: 100%,
    fill: accent-soft,
    inset: (x: 1.2em, y: 0.9em),
    radius: 3pt,
    stroke: (left: 3pt + accent),
    above: 1.1em,
    below: 1.1em,
  )[#it.body]

  // Code blocks: manifests and generated modules are where a reader slows
  // down, so give them a frame rather than letting them run into prose.
  show raw.where(block: true): it => block(
    width: 100%,
    fill: code-bg,
    inset: (x: 1.0em, y: 0.85em),
    radius: 3pt,
    stroke: 0.5pt + rule-gray,
    above: 1.1em,
    below: 1.1em,
    breakable: true,
  )[#it]

  set image(width: 100%)
  show figure: set block(above: 1.4em, below: 1.4em)
  show figure.caption: it => block(width: 92%)[
    #set text(size: 8.5pt, fill: muted, font: display-font)
    #set par(justify: false, leading: 0.5em)
    #it
  ]
  show figure.where(kind: image): it => align(center)[
    #block(stroke: 0.5pt + rule-gray, radius: 2pt, clip: true, inset: 0pt, it.body)
    #v(0.5em)
    #it.caption
  ]

  // These reports carry wide measurement tables; 8.5pt keeps them on the page.
  show table: set text(size: 8.5pt)
  set table(
    stroke: (x, y) => (
      top: if y == 0 { 0.7pt + accent } else if y == 1 { 0.5pt + rule-gray } else { 0pt },
      bottom: 0.5pt + rule-gray,
    ),
    inset: (x: 0.55em, y: 0.45em),
  )
  show table.cell.where(y: 0): set text(weight: 700, font: display-font, size: 8pt)

  show link: it => text(fill: accent, weight: 500, underline(offset: 2pt, stroke: 0.5pt + accent, it))

  body
}
