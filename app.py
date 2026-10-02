from io import BytesIO

import streamlit as st
from docxtpl import DocxTemplate

st.title("Construction Contract Generator (prototype)")

completion_date = st.date_input("By when must the work be finished?", format="DD.MM.YYYY")

doc = DocxTemplate("templates/contract_template.docx")
doc.render({"completion_date": completion_date.strftime("%d.%m.%Y")})
buffer = BytesIO()
doc.save(buffer)

st.download_button("Generate contract (Word)", data=buffer.getvalue(), file_name="contract.docx")
