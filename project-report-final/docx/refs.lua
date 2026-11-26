-- Put the bibliography under the "References" heading (before the appendices),
-- and keep front matter, References and appendices out of section numbering.
local unnumbered = {
  ["Abstract"] = true, ["List of Abbreviations"] = true, ["References"] = true,
}

function Header(h)
  local text = pandoc.utils.stringify(h.content)
  if h.level == 1 and (unnumbered[text] or text:match("^Appendix ")) then
    h.classes:insert("unnumbered")
  end
  return h
end

function Pandoc(doc)
  local blocks = pandoc.List()
  for _, b in ipairs(doc.blocks) do
    blocks:insert(b)
    if b.t == "Header" and b.level == 1 and pandoc.utils.stringify(b.content) == "References" then
      blocks:insert(pandoc.Div({}, pandoc.Attr("refs")))
    end
  end
  doc.blocks = blocks
  return doc
end
