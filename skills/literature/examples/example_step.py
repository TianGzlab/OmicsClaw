# %% [markdown]
# A local text fixture checks accession identity and exact parameter evidence.

# %%
from skills._sdk.notebook import load_skill, write_output

library = load_skill('literature')
text = 'Human brain Visium data GSE123456, gse123456 and GSM1234567; resolution=0.8.'
accessions = library.extract(text)
assert accessions.accession.tolist() == ['GSE123456', 'GSM1234567']
parameters = library.methodology(text)
assert parameters.iloc[0]['quote'] == 'resolution=0.8'
write_output(accessions, 'tables/accessions.csv')
write_output(parameters, 'tables/methodology.csv')
write_output(library.accession_figure(accessions), 'figures/accessions.png')
