// Contract v1: `document` contains tickets, mode, settings, and options.
#let opts = document.options
#set page(paper: "a4", margin: opts.margin_mm * 1mm)
#set text(font: opts.font, size: opts.font_size * 1pt)
#let per-page = opts.tickets_per_page
#let slot = (297mm - 2 * opts.margin_mm * 1mm) / per-page
#for (index, ticket) in document.tickets.enumerate() {
  if index > 0 and calc.rem(index, per-page) == 0 { pagebreak() }
  block(height: slot, width: 100%, inset: 4mm, below: 0pt, above: 0pt)[
    #align(center)[#opts.institution \
      #strong(opts.title) \
      #strong[Paper #ticket.ticket]]
    #for (number, question) in ticket.questions.enumerate() [
      #parbreak()
      #strong[#(number + 1).] #question.text
      #for choice in question.at("options", default: ()) [
        #linebreak()#choice.at(0). #choice.at(1)
      ]
    ]
  ]
}
