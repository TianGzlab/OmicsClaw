# Therapeutic Mechanism Taxonomy

Classification guide for clinical trial interventions by mechanism of action.
This reference documents the IBD taxonomy. Other disease configs are in `disease_configs/`.

## Mechanism Classes

### Anti-TNF
- **Biology:** Block tumor necrosis factor alpha (TNFα), a pro-inflammatory cytokine
- **Approved drugs:** Infliximab (Remicade), Adalimumab (Humira), Certolizumab pegol (Cimzia), Golimumab (Simponi)
- **Biosimilars:** CT-P13 (Remsima/Inflectra), SB2 (Renflexis), many others
- **Notes:** First biologic class for IBD; mature market with extensive biosimilar competition

### Anti-IL-12/23 (p40)
- **Biology:** Block shared p40 subunit of IL-12 and IL-23
- **Approved drugs:** Ustekinumab (Stelara)
- **Notes:** Targets both Th1 (IL-12) and Th17 (IL-23) pathways; broader mechanism than p19-selective

### Anti-IL-23 (p19)
- **Biology:** Selectively block IL-23 via p19 subunit; spares IL-12/Th1 pathway
- **Key drugs:** Risankizumab (Skyrizi, AbbVie), Guselkumab (Tremfya, J&J), Mirikizumab (Omvoh, Eli Lilly), Brazikumab (AstraZeneca)
- **Notes:** High-activity class; multiple Phase 3 programs. More selective than ustekinumab

### JAK Inhibitor
- **Biology:** Small molecules blocking Janus kinase signaling (JAK1, JAK2, JAK3, TYK2)
- **Key drugs:** Tofacitinib (Xeljanz, Pfizer, pan-JAK), Upadacitinib (Rinvoq, AbbVie, JAK1-selective), Filgotinib (Jyseleca, Galapagos/Gilead, JAK1-selective), Deucravacitinib (BMS, TYK2-selective)
- **Notes:** Oral small molecules; safety monitoring required (cardiovascular, infections, malignancy)

### Anti-Integrin
- **Biology:** Block leukocyte trafficking to gut via integrin receptors
- **Key drugs:** Vedolizumab (Entyvio, **Takeda**, gut-selective α4β7), Natalizumab (Tysabri, α4-integrin), Etrolizumab (Roche, α4β7/αEβ7), Ontamalimab (anti-MAdCAM-1)
- **Takeda relevance:** Vedolizumab (Entyvio) is Takeda's flagship IBD product
- **Notes:** Gut-selective mechanism attractive for safety profile

### S1P Modulator
- **Biology:** Sequester lymphocytes in lymph nodes by modulating sphingosine-1-phosphate receptors
- **Key drugs:** Ozanimod (Zeposia, BMS), Etrasimod (Velsipity, Pfizer/Arena)
- **Notes:** Oral, non-JAK mechanism; growing class

### Anti-TL1A
- **Biology:** Block TNF-like ligand 1A (TL1A/TNFSF15), involved in mucosal inflammation and fibrosis
- **Key drugs:** Duvakitug (PRA023, **Sanofi**/Prometheus origin), Tulisokibart (MK-7240, **Merck/MSD**), TEV-48574 (**Teva**)
- **Competitive landscape:** Multiple companies racing — Merck/MSD, Sanofi, Teva, Biocad
- **Notes:** Emerging hot target; potential anti-fibrotic benefit unique among IBD mechanisms. Multiple companies racing

### Cell Therapy
- **Biology:** Autologous or allogeneic cell-based therapies (MSCs, Tregs)
- **Notes:** Mostly early-phase for perianal Crohn's disease fistulas

### Microbiome / FMT
- **Biology:** Restore gut microbiome via fecal microbiota transplant or defined consortia
- **Notes:** Active research area; several defined-consortium products in trials

### Anti-IL-6
- **Biology:** Block IL-6 or IL-6 receptor signaling
- **Key drugs:** Olamkicept (sgp130Fc, selective IL-6 trans-signaling blocker)
- **Notes:** Smaller class in IBD

### PDE4 Inhibitor
- **Biology:** Inhibit phosphodiesterase 4, reducing intracellular cAMP degradation and dampening inflammatory signaling
- **Key drugs:** Apremilast (Otezla)
- **Notes:** Oral small molecule; primarily studied in psoriasis/psoriatic arthritis, limited IBD data

### Anti-IL-36
- **Biology:** Block IL-36 receptor signaling, part of the IL-1 superfamily involved in mucosal innate immunity
- **Key drugs:** Spesolimab (Spevigo, Boehringer Ingelheim), Imsidolimab
- **Notes:** Emerging target; spesolimab approved for generalized pustular psoriasis, under investigation in IBD

### GLP-1 / Metabolic
- **Biology:** Glucagon-like peptide-1 receptor agonists and related metabolic modulators with potential anti-inflammatory effects
- **Key drugs:** Semaglutide (Ozempic/Wegovy), Tirzepatide (Mounjaro), Liraglutide
- **Notes:** Primarily metabolic agents; IBD trials exploring anti-inflammatory co-benefits in obese IBD patients

### Anti-p19/TL1A Bispecific
- **Biology:** Bispecific antibodies simultaneously targeting IL-23 p19 and TL1A for dual pathway blockade
- **Notes:** Very early-stage; combines the two most promising emerging IBD targets into a single molecule

## Classification Priority

The classifier checks mechanisms in this order (most specific first):
1. Anti-TL1A (unique drug names, low ambiguity)
2. Anti-IL-23 (p19) (specific drug names)
3. Anti-IL-12/23 (p40) (ustekinumab only)
4. Anti-TNF (well-known drugs)
5. JAK Inhibitor
6. Anti-Integrin
7. S1P Modulator
8. Anti-IL-6
9. PDE4 Inhibitor
10. Anti-IL-36
11. GLP-1 / Metabolic
12. Anti-p19/TL1A Bispecific
13. Cell Therapy
14. Microbiome / FMT
15. Other Biologic (fallback for BIOLOGICAL type)
16. Small Molecule (Other) (fallback for DRUG type)
17. Non-pharmacological (DEVICE, BEHAVIORAL, etc.)
18. Unclassified (no intervention info)
