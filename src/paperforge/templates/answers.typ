// `answer_text` is derived from the validated inline answer by Paperforge.
#let opts = document.options
#set page(paper: "a4", margin: opts.margin_mm * 1mm)
#set text(font: opts.font, size: opts.font_size * 1pt)
#opts.institution
#heading(level: 1)[#opts.title — Answers]
#for ticket in document.tickets [
  #heading(level: 2)[Paper #ticket.ticket]
  #for (number, question) in ticket.questions.enumerate() [
    #parbreak()
    #strong[#(number + 1). #question.text]
    #for choice in question.at("options", default: ()) [
      #linebreak()#choice.at(0). #choice.at(1)
    ]
    #parbreak()
    #strong[Answer:] #question.answer_text
  ]
]
