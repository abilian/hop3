// Hop3 — experience-report bundle style.
//
// Adapted from ~/projects/research/econ-papers/ai-strategy/notes/econ-lab-brief.typ
// (Abilian Econ Lab policy brief), minus the logo lockup: this bundle has no
// mark, so the letterhead is a rule and the running header is text.
//
// Applied by bundle.typ, which build.py generates. The per-report `.typ` parts
// are md2typst output with their own preamble stripped, so this file owns every
// visual decision in the document.

// ============================================================================
// Palette — Hop3 slate. Deliberately not the Econ Lab teal: these are different
// publications and should not be mistaken for one another at a glance.
// ============================================================================

#let accent      = rgb("#1f4e5f")
#let accent-soft = rgb("#eef3f5")
#let rule-gray   = luma(210)
#let muted       = luma(95)
#let ink         = rgb("#0d1117")

#let body-font    = ("Charter", "IBM Plex Serif", "Source Serif Pro", "Libertinus Serif", "New Computer Modern")
#let display-font = ("Inter", "IBM Plex Sans", "Source Sans Pro", "Atkinson Hyperlegible", "Helvetica Neue")
#let mono-font    = ("JetBrains Mono", "IBM Plex Mono", "SF Mono", "DejaVu Sans Mono")

#let org-name = "Abilian — Hop3"
#let org-url  = "hop3.cloud"

// Every H1 in the body is one report, so a page break before each is what makes
// the bundle read as a collection of chapters. The first one is suppressed:
// otherwise the cover is followed by a blank page.
#let seen-h1 = counter("hop3-report")

#let to-str(c) = {
  if type(c) == str { c } else if type(c) != content { "" } else if c.has("text") {
    c.text
  } else if c.has("children") {
    c.children.map(to-str).join("")
  } else if c.has("body") { to-str(c.body) } else { "" }
}

#let bundle(
  title: "",
  subtitle: none,
  date: none,
  status: none,
  paper: "a4",
  body,
) = {
  set document(title: title, author: org-name)

  set page(
    paper: paper,
    margin: (top: 2.4cm, bottom: 2.2cm, left: 2.5cm, right: 2.5cm),
    numbering: "1",

    // Pages 2+: publication left, current report right. `here()` keeps the
    // right-hand side following the section the reader is actually on.
    header: context {
      if counter(page).get().first() > 1 {
        let chapters = query(heading.where(level: 1).before(here()))
        let current = if chapters.len() > 0 { to-str(chapters.last().body) } else { "" }
        grid(
          columns: (auto, 1fr),
          align: (left + horizon, right + horizon),
          text(size: 8pt, fill: muted, font: display-font, tracking: 0.4pt)[#org-name],
          text(size: 8pt, fill: muted, font: display-font)[#current],
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
  show raw: set text(font: mono-font, size: 8.8pt)

  // --- cover -------------------------------------------------------------
  block(above: 3.5cm, below: 1.1em)[
    #set text(font: display-font, weight: 700, size: 24pt, fill: ink, hyphenate: false)
    #set par(leading: 0.5em, justify: false)
    #title
  ]
  if subtitle != none and subtitle != "" {
    block(below: 1.0em)[
      #set text(font: display-font, weight: 400, size: 13pt, fill: luma(70), hyphenate: false)
      #set par(leading: 0.55em, justify: false)
      #subtitle
    ]
  }
  {
    let parts = ()
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

  v(1.6em)
  block[
    #set text(font: display-font, weight: 600, size: 11pt, fill: accent)
    Contents
  ]
  v(0.4em)
  outline(title: none, depth: 1, indent: 0em)

  pagebreak(weak: true)

  // --- headings ----------------------------------------------------------
  // H1 = one report. `weak: false` because a report must start on a fresh page
  // even when the previous one happened to end near the bottom.
  show heading.where(level: 1): it => {
    context {
      if seen-h1.get().first() > 0 { pagebreak() }
    }
    seen-h1.step()
    block(above: 0em, below: 0.9em)[
      #set text(font: display-font, weight: 700, size: 18pt, fill: ink, hyphenate: false)
      #set par(leading: 0.5em, justify: false)
      #show link: l => l.body
      #it.body
    ]
    line(length: 100%, stroke: 0.6pt + accent)
    v(0.9em)
  }

  show heading.where(level: 2): it => block(above: 1.9em, below: 0.9em)[
    #set text(font: display-font, weight: 700, size: 13pt, fill: accent, hyphenate: false)
    #show link: l => l.body
    #set par(justify: false, leading: 0.55em)
    #it.body
  ]

  show heading.where(level: 3): it => block(above: 1.5em, below: 0.7em)[
    #set text(font: display-font, weight: 600, size: 11pt, fill: luma(50), hyphenate: false)
    #show link: l => l.body
    #set par(justify: false, leading: 0.5em)
    #it.body
  ]

  show heading.where(level: 4): it => block(above: 1.3em, below: 0.6em)[
    #set text(font: display-font, weight: 500, size: 10pt, fill: luma(80), style: "italic", hyphenate: false)
    #set par(justify: false)
    #it.body
  ]

  // Bold carries the lead sentence of each finding in these reports, so give it
  // weight and ink rather than colour, which would fight the accent headings.
  show strong: it => text(weight: 700, fill: ink)[#it.body]

  set list(indent: 0.6em, body-indent: 0.6em)
  set enum(
    indent: 0.4em,
    body-indent: 0.5em,
    numbering: n => text(fill: accent, weight: 600)[#n.],
  )

  // Blockquotes: the reports use them for withdrawal banners and for retained
  // text from a superseded report, both of which want setting apart.
  show quote.where(block: true): it => block(
    width: 100%,
    fill: accent-soft,
    inset: (x: 1.2em, y: 0.9em),
    radius: 3pt,
    stroke: (left: 3pt + accent),
    above: 1.0em,
    below: 1.0em,
  )[#it.body]

  // Screenshots are wide and land two-per-report; cap them so a pair does not
  // push a section onto its own page.
  show image: it => align(center, block(
    stroke: 0.5pt + rule-gray,
    radius: 2pt,
    clip: true,
    it,
  ))
  set image(width: 82%)

  show table: set text(size: 9pt)
  set table(stroke: (x, y) => (
    top: if y == 0 { 0.7pt + accent } else if y == 1 { 0.5pt + rule-gray } else { 0pt },
    bottom: 0.5pt + rule-gray,
  ))

  show link: it => text(fill: accent, weight: 500, underline(offset: 2pt, stroke: 0.5pt + accent, it))

  body
}
