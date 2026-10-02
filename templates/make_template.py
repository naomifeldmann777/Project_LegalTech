from docx import Document

doc = Document()
doc.add_heading("Construction Contract (test)", level=1)
doc.add_paragraph("The Contractor shall complete the Works by {{ completion_date }}.")
doc.save("templates/contract_template.docx")
print("Template created.")
