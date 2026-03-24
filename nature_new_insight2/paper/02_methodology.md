# Detailed Methodology — # Tissue-resident memory CD8 T cell diversity is spatiotemporally imprinted

# # Tissue-resident memory CD8 T cell diversity is spatiotemporally imprinted

**Source**: s41586-024-08466-x.pdf
**DOI**: https://doi.org/10.1038/s41586-024-08466-x

**Authors**: Miguel Reina-Campos,7, Alexander Monell,7, Amir Ferry1, Vida Luna1, Kitty P. Cheung1, Giovanni Galletti1, Nicole E. Scharping1, Kennidy K. Takehara1, Sara Quon1, Peter P. Challita1, Brigid Boland4, Yun Hsuan Lin4, William H. Wong4, Cynthia S. Indralingam4, Hayley Neadeau2, Suzie Alarcón2, Gene W. Ye et al.

## Metadata

| Field | Value |
|-------|-------|
| Organism | Homo sapiens, Mus musculus |
| Technology | Visium HD, 10x Visium, Xenium, MERSCOPE, 10x Chromium, snRNA-seq, scRNA-seq, Bulk RNA-seq |
| Tissue | small intestine, colon, brain |

> This file contains the **complete, untruncated** methods from the paper. The planner-agent should read this in its entirety before formulating any experiment plan.

## Methods: Mice

Mice were maintained in specific-pathogen-free conditions at a temperature between 18 °C and 23 °C with 40–60% humidity and a 12 h–12 h light–dark cycle in accordance with the Institutional Animal Care and Use Committee of the University of California, San Diego (UCSD). All mice were of C57BL/6J background and bred at the UCSD or purchased from The Jackson Laboratory.R26creERT2 (stock no. 008463, The Jackson Laboratory),Tgfbr2fl/fl (stock no. 012603, The Jackson Laboratory), P14 Cas9–eGFP (stock no. 026179, The Jackson Laboratory), P14 and CD45.1 congenic mice were bred in-house. Male recipient mice were used for adoptive transfer experiments, and females were used as P14 CD8 T cell donors. In the spatial pooled CRISPR knockout experiment, a male was used as a donor. To delete floxed alleles using Cre-ERT2, 1 mg of tamoxifen (Cayman Chemical) emulsified in 100 µl of sunflower seed oil (Sigma-Aldrich) was administered by intraperitoneal injection for five consecutive days to P14R26creERT2Tgfbr2WT(WT) and P14R26creERT2Tgfbr2fl/fl (TGFβRII knockout) mice before P14 CD8 T cell isolation. All mice were between 1.5 and 6 months old at the time of infection and randomly assigned to experimental groups. No statistical methods were used to predetermine sample sizes, but our sample sizes are similar to those reported in previous publications from our laboratory and others. No blinding was performed during mouse experiments. Investigators were not blinded to group allocation during data collection and/or analysis. Mice were fed ad libitum for the specified amount of time. All animal studies were approved by the Institutional Animal Care and Use Committee at the UCSD and performed in accordance with UCSD guidelines.

## Methods: Adoptive cell transfer of naive P14 CD8 T cells and LCMV infection in mice

A total of 5 × 104female naive P14 CD8 T cells isolated by negative enrichment using magnetic activated cell sorting (MACS) and resuspended in PBS were transferred intravenously into congenically distinct male recipient mice. Recipient mice were subsequently infected intraperitoneally with 2 × 105 plaque-forming units of the Armstrong strain of LCMV.

## Methods: Preparation of single-cell suspensions for flow cytometry

The isolation of CD8 T cells was performed as described previously38. SI intraepithelial lymphocytes and lamina propria lymphocytes were prepared by removing Peyer’s patches and the luminal contents from the entire SI. The SI was then cut longitudinally into 1 cm pieces and incubated at 37 °C for 30 min in HBSS with 2.1 mg ml−1 sodium bicarbonate, 2.4 mg ml−1 HEPES, 8% bovine growth serum and 0.154 mg ml−1 dithioerythritol (EMD Millipore). The samples were passed through a 70-µm cell strainer, and the supernatant constituted the intraepithelial lymphocyte compartment of the SI. The remaining tissue fragments of the SI were further incubated in RPMI with 1.2 mg ml−1 HEPES, 292 µg ml−1 l-glutamine, 1 mM MgCl2, 1 mM CaCl2, 5% fetal bovine serum (FBS) and 100 U ml−1 collagenase (Worthington) at 37 °C for 30 min. After enzymatic incubation, samples were filtered through a 70-µm nylon cell strainer (Falcon). Tissue preparations were separated on a 44%/67% Percoll density gradient.

The following antibodies were used for flow cytometry: CD3 (PE clone 145-2C11, eBioscience 12-0031-83, 1:200 dilution), TCR αβ (APC clone H57-597, eBioscience 17-5961-83, 1:200 dilution), NK1.1 (FITC clone PK136, eBioscience 11-5941-81, 1:400 dilution), CD19 (PerCP-Cy5.5 clone eBio1D3, eBioscience 45-0193-82, 1:200 dilution), CD8b (BV421 clone H35-17.2, eBioscience 48-0083-82, 1:400 dilution), CD45.1 (BV510 clone A20, BioLegend 110741, 1:200 dilution), TCR γδ (BV711 clone GL3, BioLegend 118149, 1:200 dilution), CD4 (BV786 clone GK1.5, BioLegend 100453, 1:400 dilution), CD8a (PE-Cy7 clone 53-6.7, eBioscience 25-0081-82, 1:400 dilution), fixable viability dye (APC-Cy7 eBioscience 65-0865-14, 1:1,000), CD11b (PE clone M1/70, eBioscience

12-0112-82, 1:200 dilution), CD11c (APC clone N418, BioLegend 117310, 1:200 dilution), Ly6C (FITC clone AL-21, BD 553104, 1:200 dilution), Ly6G (PerCP-Cy5.5 clone 1A8, BioLegend 127615, 1:200 dilution), XCR1 (BV421 clone ZET, BioLegend 148216, 1:200 dilution), CD45 (BV510 clone 30-F11, BD 561487, 1:200 dilution), F4/80 (BV711 clone BM8, BioLegend 123147, 1:200 dilution), MHC II (BV786 clone M5/114.15.2, BioLegend 107645, 1:200 dilution) and B220 (PE-Cy7 clone RA3-6 B2, BioLegend 103222, 1:200 dilution).

## Methods: Sample preparation for histology of the mouse SI

For fresh frozen samples, mouse SIs were collected, retaining the proximal–distal orientation. After discarding the first 3 cm proximal section, approximately 10 cm of mouse proximal SI (containing duodenum and proximal jejunum) was rinsed in ice-cold PBS and the lumen contents were flushed with 20 ml of ice-cold PBS using a gavage syringe. The SI was then loaded onto a 3.25-mm-diameter knitting needle premoistened with cold PBS and placed directly on thick blotting paper. The Mouse Intestinal Slicing Tool39 was used as a guide for the scalpel to cut the intestine longitudinally along the knitting needle. The Mouse Intestinal Slicing Tool and needle were removed, and the SI was spread open and rolled using a wood autoclaved round toothpick, embedded in OCT in plastic moulds, frozen in dry ice(Tissue-Tek Cryomold) and kept at −80 °C until cryosectioning. For fixed frozen samples, the opened cleaned SIs were fastened to blotting paper by minutien pins in each corner and fixed in 4% paraformaldehyde solution in PBS at 4 °C for 16 h, followed by incubation in 70% ethanol at 4 °C for a minimum of 3 h. The SI samples were then rolled using a wood autoclaved round toothpick, snap-frozen in OCT in plastic moulds for cryosection (Tissue-Tek Cryomold) and kept at −80 °C until processing. For formalin-fixed paraffin-embedded (FFPE) samples, fixed SIs were rolled, mounted on 2% agar round moulds and placed on histology cassettes for paraffin embedding.

## Methods: Histology and immunofluorescence staining of fresh frozen mouse tissues

After OCT block equilibration at −20 °C, 10-mm slices were obtained using a cryostat, mounted on glass slides, dried for 20 min at −20 °C and fixed in ice-cold acetone at −20 °C for 20 min. After fixation, the slides were dried briefly at room temperature and stored at −80 °C until stained or used immediately. For staining, the slides were equilibrated at room temperature, washed in 4 °C PBS twice for 5 min, blocked in serum-free blocking reagent overnight (Dako) at 4 °C, followed by staining with CD45.1–AF594 (BioLegend, clone A20, 110756, 1:50 dilution) and E-cadherin-APC (BioLegend, clone DECMA-1, 147312, 1:200 dilution) and CD8a–FITC (BioLegend, clone 53-6.7, 35-0081-U500, 1:50 dilution) diluted in antibody diluent solution (Dako, S080983-2) overnight at 4 °C, stained with DAPI and mounted with coverslips using Vectashield Vibrance Antifade mounting medium (VectorLabs, H-1700). Images were acquired on an Olympus VS200 Slide Scanner (UCSD Microscopy Core) or on a Zeiss LSM700 confocal microscope. P14 CD8 T cell distances for IMAP representation over time were quantified using a groovy script on QuPath (https://github.com/Goldrathlab/ Spatial-TRM-paper).

## Methods: Single-nucleus RNA-seq of mouse SI

Female CD45.1+CD8+ P14 T cells were adoptively transferred into male CD45.2 recipients (1 × 105cells per mouse) 30 min before infection with the Armstrong strain of LCMV. At 28 d.p.i., the mice were euthanized and the SI was dissected, flayed and washed in cold PBS; Peyer’s patches were excised from the SI. The SI was divided into three equal sections designated as the proximal, middle and distal SI. Tissue sections were cut into pieces of approximately 3 mm and flash-frozen in liquid nitrogen for 2 min. Nucleus isolation was performed with 10x Genomics Chromium Nuclei Isolation Kit per the manufacturer’s instructions. In brief, 30–50 mg of flash-frozen tissue per sample was dissociated

with a pestle, incubated for 10 min on ice and washed. Dissociated tissue was passed through a nucleus isolation column, and flowthrough nuclei were washed in debris removal buffer and wash and resuspension buffer. Nuclei were quantified with a Nexcelom Bioscience Cellometer. For maximum targeted recovery, 40,000 nuclei per sample were loaded for Gel Bead-In Emulsion generation. Samples were processed by the Chromium Next GEM Single Cell 3′ HT Dual Index v3.1 protocol and sequenced to a depth of 550 million read pairs per sample (around 23,000 read pairs per nucleus) on a NovaSeq 6000 system (Illumina).

## Methods: Spatial transcriptomics analysis using whole-genome spatial transcriptomics (VisiumHD)

A 7-µm-thick section from an 8 d.p.i. FFPE sample was placed in a histology slide, dried at 42 °C for 3 h, dehydrated overnight, baked at 60 °C for 30 min and deparaffinized following the VisiumHD stand-

- ard protocol (CG000685). The mouse reagents (VisiumHD, Mouse Transcriptome, 6.5 mm, four reactions, PN-1000676) were used to obtain high-quality H&E images, perform hybridization, RNA removal and probe amplification, carry out analyte transfer to the VisiumHD slide using the Cytassist with the 2.0 software, and generate libraries, which were sequenced following the recommended configuration in a NovaSeq 6000 Illumina instrument. Binary base call files were demultiplexed into FASTQ files using spaceranger mkfastq followed by spaceranger count to generate the spatial representation of gene counts by matrix at 2-mm-resolution and 8-mm-resolution binning. A Cellpose40cell-segmentation model was fine-tuned to segment nuclei in the high-resolution VisiumHD H&E image. A cell-by-gene matrix was created by summing transcript counts in all 2 mm bins overlapping each cell in the segmentation mask. gimVI was used to jointly embed cells from an 8 d.p.i. Xenium dataset with those from 8 d.p.i. VisiumHD41. The crypt–villus axis and cell types for VisiumHD were imputed by using the three closest Xenium neighbours in the joint latent space. The crypt–villus axis values were calculated as the mean of the neighbours’ values, whereas the cell type was determined by the most frequently occurring type among the neighbours. Further details of the downstream analysis of the VisiumHD dataset are provided at GitHub (https://github.com/Goldrathlab/Spatial-TRM-paper).

## Methods: Spatial transcriptomics analysis using multiple error-robust fluorescence in situ hybridization

Fresh frozen tissue was sectioned according to standard histology procedures to a thickness of 10 µm. The sections were adhered to the MERSCOPE slides (Vizgen, 20400001) coated with fluorescent beads by storing them in the cryostat at −20 °C for at least 5 min. The samples were fixed in 5 ml of fixation buffer containing 4% paraformaldehyde in 1× PBS that was preheated to 47 °C and incubated for 30 min at 47 °C, according to the MERSCOPE Quick Guide Modified Fixation for Fresh Frozen Samples. The samples were then washed three times with 5 ml PBS, 5 min each time. The samples were permeabilized in 5 ml 70% ethanol at 4 °C in parafilm-sealed dishes overnight and stored in these conditions for up to a month. Samples were then prepared according to Vizgen’s protocols, starting from the cell-boundary protein-staining step. The samples were hybridized with a custom 500-gene panel that included 5 sequential genes, as well as several blank barcodes that do not encode a gene and used for measuring the background signal. To clear the samples of lipids and proteins that interfere with imaging, 5 ml of Clearing Premix (Vizgen, 20300003) was mixed with 100 µl of proteinase K for each sample, and the samples were placed at 47 °C in a humidified incubator overnight (or for a maximum of 24 h) and then moved to 37 °C. The samples were stored in the clearing solution provided with the MERSCOPE kit in the 37 °C incubator before imaging for up to a week. The samples were imaged on the MERSCOPE according to the MERSCOPE Instrument User Guide. Seven 1.5-µm-thickz planes were imaged for each field of view at 60× magnification. Images were decoded to RNA spots withxyz and gene ID using the Merlin software

of Vizgen. Cell segmentation was performed using the Cellboundary algorithm, relying on the Cellboundary 2 stain and DAPI nuclear seeds.

## Methods: Spatial transcriptomics analysis using 10x Xenium

FFPE tissues were sectioned to a thickness of 5 µm onto a Xenium slide, followed by deparaffinization and permeabilization following the 10x user guides CG000578 and CG000580. Probe hybridization, ligation and amplification were done following the 10x user guide CG000582. In brief, probe hybridization occurred at 50 °C overnight with a probe concentration of 10 nM using a custom gene panel designed to detect 350 different mRNAs. After stringent washing to remove unhybridized probes, probes were ligated at 37 °C for 2 h. During this step, a rolling circle amplification primer was also annealed. The circularized probes were then enzymatically amplified (2 h at 37 °C), generating multiple copies of the gene-specific barcode for each RNA binding event. After washing, background fluorescence was quenched chemically. The sections were placed into an imaging cassette to be loaded onto the Xenium Analyzer instrument following the 10x user guide CG000584.

## Methods: Spatial data processing

For 10x Xenium spatial transcriptomics data, nuclei were segmented using a fine-tuned Cellpose40 model on maximum-projected DAPIstaining images. Baysor42 was used to predict cell-boundary segmentations using transcript identity and positions, and the prior Cellpose nuclei segmentation or Cellboundary 2 segmentation for 10x Xenium or MERSCOPE, respectively. The parameter prior-segmentation-confidence was set to 0.95 for 10x Xenium and to 0.9 for MERSCOPE, and min-molecules-per-cell was set to the median nucleus transcript count (https://github.com/Goldrathlab/Spatial-TRM-paper#preprocessing). Baysor segmentations containing no nuclei were filtered out, and segmentations containing multiple nuclei were split by assigning transcripts to the nearest nucleus centroid in the segmentation boundary. Cell boundaries are visualized as polygons using the alphashape Python package. All cells withn < 8 nuclear transcripts,n < 20 total transcripts orn > 800 total transcripts were filtered out before downstream processing. To integrate spatial replicates into a joint embedding, scVI43 was used with n_layers of 2 and n_latent of 30. The joint embedding was projected into two-dimensional space using scVI.model.utils.mde. Leiden clustering was performed on the scVI learned embeddings using scanpy.tl.leiden with a resolution of 1, and every Leiden cluster was further subclustered at a resolution of 1.2. Celltypist44 and GeneFormer45 were used for a first-pass cell type assignment, with further manual refinement based on the expression of cell type marker genes to define cell types in a class > type > subtype hierarchy. The Anndata46 format was used for all further processing. To align histology images with Xenium spatial coordinates, we used an OpenCV Oriented FAST and Rotated BRIEF47 object to detect key points in the DAPI channel of both histology and Xenium images. These key points were then matched using an OpenCV DescriptorMatcher, enabling the computation of a homography matrix based on the top matches using cv2.findHomography. Subsequently, histology images across all channels underwent warping using this homography matrix with cv2.warpPerspective. To align H&E images with Xenium spatial coordinates, we trained a pix2pix generative adversarial network48,49 to predict DAPI images from H&E as an intermediate state before finding key points and matching, as previously mentioned. To visualize mouse transcriptional signatures onto human datasets, all (n = 8) mice time course samples were used to find the top 15 differentially expressed genes (Scanpy rank_genes_groups and method = ‘wilcoxon’) between P14 cells gated to the crypt and P14 cells gated to the top of villi. Human homologues of these 15 genes are defined as UCell50 signatures and mapped to human CD8αβ T cells. Human CD8αβ T cells are positioned on IMAPs and coloured by their enrichment of the (left) top mouse signature and (right) crypt mouse signature. All codes to analyse the spatial datasets are available at https:// github.com/Goldrathlab/Spatial-TRM-paper.

## Methods: Histological staining of mouse intestinal tissue after Xenium analysis

After the Xenium run, slides were kept hydrated in PBS-T (0.05% Tween-20 in PBS) at 4 °C. For post-Xenium immunofluorescence staining, PBS-T was removed and samples were blocked using universal blocking reagent CAS-Block and stained with anti-CD8a antibody (Abcam, EPR21769) 1:50 dilution) overnight at 4 °C, followed by three washes with PBS. Anti-rabbit AF594 secondary antibody (Invitrogen, A-11012, 1:200 dilution) in Dako antibody diluent was then added for 1 h at room temperature in the dark, followed by three washes with PBS. The slides were then stained using WGA–FITC followed by DAPI staining and then mounted with a coverslip using Vectashield mounting medium. The slides were dried for 1 h at room temperature in the dark before imaging with an Olympus VS200 Slide Scanner at 20×. The slides were then soaked in PBS at 4 °C overnight to dismount the coverslip and subsequently washed three times in PBS and twice in ddH2O before proceeding with H&E staining. The coverslip was mounted using xylene-based mounting medium (Cytoseal XYL Epredia), and the slides were dried for 1 h and imaged used VS200 Slide Scanner at 20×.

## Methods: Human samples

Deidentified human FFPE samples from healthy participants were acquired from the San Diego Digestive Diseases Research Center. Slices of 5 mm were obtained using a microtome, deparaffinized and H&E stained according to common histology practices or processed according to the 10x Xenium protocol.

## Methods: Human participants and ethical statement

The Human Research Protection Programs at the UCSD reviewed and approved the protocol, including a waiver of consent. Submucosal ileal biopsies were obtained from patients who underwent colonoscopies to rule out inflammatory bowel diseases. Ileal biopsies were evaluated by a pathologist and found to be normal without histological inflammation. Samples were deidentified and processed for the study.

## Methods: Gene panel design for probe-based spatial transcriptomics profiling of mouse SI

The gene panel design made use of Predictive and Robust Gene Selection for Spatial Transcriptomics (PERSIST)19, a deep learning model that uses single-cell RNA sequencing (scRNA-seq) data to learn a binary mask for the identification of a subset of genes that best predict cell type from gene expression (supervised) or for the reconstruction of whole-transcriptome gene expression (unsupervised). For the Xenium mouse 350-gene panel, 79 SI canonical cell type marker genes were compiled from existing literature andXist, a marker for transferred female P14 CD8 T cells. An additional 158 genes from a Nichenet database21of ligand– receptor pairs were included. Next, supervised PERSIST was run on an immune-enriched gut scRNA-seq dataset51with the previously compiled set of genes as prior information, adding an additional 70 genes. Finally, supervised PERSIST was run on a SI scRNA-seq dataset to capture 59 cell type marker genes for 350 total targets. To create the Xenium human 422-gene panel, we created a base set of canonical immune marker genes, ligand–receptor pairs, spatially differentially expressed genes in mouse P14 CD8 T cells, and the 10x Genomics base human colon panel totalling 343 genes. Using this set as prior information for PERSIST, and a reference human immune cell scRNA-seq dataset52, unsupervised PERSIST filled in the remaining 79 genes. To create the 494-gene panel for MERSCOPE, we compiled 18 published bulk RNA-seq datasets profiling different immune populations in different disease settings5,53–66, including the ImmGen RNAseq database (immgen.org), and manually curated metadata attributes for each sample for the following categories: cell. main, cell.type, cell.subtype, cell.state, model and tissue. The annotated integrated dataset compilation was used as input for feature selection with XGBoost67. Top genes in each attribute were incorporated as the

panel backbone. Furthermore, gene markers of intestinal cell markers from PanglaoDB and ref. 68, ImmGen CITE-seq protein markers and 159 genes from the ligand–receptor database NicheNet21 were added. A total of 494 final genes passed the quality-check filtering of Vizgen for transcript length and expression levels. The Xenium mouse 480-gene panel was designed using the 350-gene panel but removing genes that were minimally informative based on the time course data and adding genes that were relevant based on manual curation and a prioritization score that evaluates their ability to differentiate clusters in a scRNA-seq dataset containing most cell types of the mouse SI69.

## Methods: Defining structural axes in spatial transcriptomics datasets of the SI

To calculate the longitudinal axis, a multiline segment was initially labelled across the base of the basal membrane, using labelme70, starting from the outermost section of the roll. For each cell, the nearest neighbour was calculated from the set of all locations on the multiline segment positioned closer to the centre of the SI roll. The relative position of the nearest neighbour along the length of the entire multiline segment was used as the longitudinal position. In datasets with atypical morphology, longitudinal axis values for each cell were predicted using a deep neural network trained on a feature space of transcriptional neighbourhood decomposition latent factors and multiline segments marking the base of the basal membrane, the top of each villus and the middle of each villus. Transcriptional neighbourhood decomposition was performed using Scikit-learn71 non-negative matrix factorization on a matrix of the summed transcript count values for the ten nearest neighbours of each cell, calculated with a SciPy72K-dimensional tree, to create a transformed data matrix W with 15 latent factors. To calculate the crypt–villus axis, a fine-tuned Cellpose model was used to segment villi on the basis of WGA staining in Xenium samples and cell spatial positions in MERSCOPE samples. The distance between each cell and the base of the basal membrane was calculated as before, and these values were z-score scaled among cells in the same segmented villus. For datasets with poorly defined morphology, crypt–villus axis values for each cell were predicted using a TensorFlow v2.18.0 (https:// www.tensorflow.org/) deep neural network trained on a feature space comprising a decomposition of latent factors for epithelial and stromal transcriptional neighbourhoods. Transcriptional neighbourhood decomposition was performed by fitting a non-negative matrix factorization model on a matrix of the summed transcript count values (10, mouse; 30, human) for the nearest epithelial and stromal neighbours of each cell in all datasets to avoid the influence of variability in immune populations at different infection states. Crypt–villus axis predictions for each cell were smoothed over their nearest 150 neighbouring cell predictions in human data. To calculate the epithelial axis, the mean distance from each cell to the five nearest epithelial cells was divided by the mean distance to the five nearest cells of any cell type. The resulting values werez-score scaled and clipped at an upper bound to align epithelial distances between the villus and basal membrane.

## Methods: Generation of IMAPs and transcriptional IMAPs

The epithelial IMAP axis values were computed through a biexponential transformation applied to the clipped epithelial axis values across all cells. Each cell was positioned on the IMAP according to its corresponding crypt–villus axis and transformed epithelial axis values. The density in the scattered point cloud was visualized using colour-mapped scipy. stats.gaussian_kde values, with density lines overlaid using seaborn. kdeplot for enhanced clarity and interpretation. Gate boundaries were drawn manually to distinguish the muscularis, villus crypt and villus top by observing the IMAP locations of cell types known to localize to each region. Transcriptional IMAPs were coloured by adding an array of gene expression counts as a point weight parameter to the scipy. stats.gaussian_kde function. Similarly, gene signature IMAPs were coloured using the squared UCell signature enrichment scores as the

point weight parameter. In human IMAPs, signature and gene expression point weights were squared to overcome bias in CD8αβ+ physical density in IMAP visualization.

## Methods: Statistical analysis

In Fig. 2e, significance cut-offs are set at absolute Spearman ρ > 0.05, an arbitrary threshold used to highlight differences between axes. The Spearman coefficients for each gene and their correspondingP values

- are documented in Supplementary Table 3 acrossn = 87,387 P14 T cells. In Extended Data Fig. 7a, the top four differentially expressed genes per condition across P14 cells (n = 4,135 WT,n = 4,161 TGFβR2 knockout) are calculated using Wilcoxon testing with Benjamini–Hochberg correction in the function scanpy.tl.rank_genes_group. In Extended Data Fig. 7d,e,


- a non-parametric two-sample Kolmogorov–Smirnov statistic is used to calculate the significance of the difference between P14 cell type proximity distributions in wild-type and TGFβR2 knockout conditions. A cut-off of similarity is arbitrarily positioned at a Kolmogorov–Smirnov statistic of 0.08, corresponding to a correctedP value of approximately 1 × 10−12 to 1 × 10−10 (Kolmogorov–SmirnovP values vary with the number of samples in the compared distributions). Kolmogorov–Smirnov tests are documented in Supplementary Table 8. In Fig. 4d,f and Extended Data Fig. 1h, gene-expression counts were log-normalized, and two-sample, two-sided t-tests were used to test for significant differences in mean gene expression pairwise between perturbation groups at a significance level of 0.05 and Benjamini–Hochberg correction for P values in each pairwise group. A similar approach was used in Extended Data Fig. 8e using raw detected barcode numbers without normalization. For each subplot in Extended Data Fig. 1g, we applied one-way and two-way analyses of variance, with Dunnett’s method for multiple comparisons. In Extended Data Fig. 1j,k, we used a one-way analysis of variance followed by Tukey’s honestly significant (HSD) difference tests to create confidence intervals. In Extended Data Fig. 9g, human gene expression counts were log-normalized before differentially expressed genes were calculated between human CD8αβ T cells gated to different regions using a two-tailed Wald test in the Python package diffxpy.P values were adjusted using a Benjamini–Hochberg correction. Data are mean ± s.e.m. in all the figures.

## Methods: Cloning and making retrovirus

The LsgC plasmid was generated by using PCR to linearize the backbone of the LsgA plasmid and exclude the Ametrine reporter gene73. NEBuilder HiFi DNA Assembly was then used to insert a HA-tagged mCherry sequence, synthesized by Integrated DNA Technologies (IDT), into the open site. ChopChop was used to design sgRNAs targeting mouseCd19,Thy1 andCxcr3 (ref. 74). Forward (5′-CACCN) and reverse (5′-AAACN) primers forming the sgRNAs were synthesized by IDT. Each sgRNA was assigned a 388-bp or 390-bp barcode, containing seven or eight probe hybridization sites, respectively. These sites corresponded to one of the three lowest-expressed genes in SI P14 CD8 T cells from the SI spatial transcriptomics time course: Muc5ac, Neurog3 and Fer1l6 (Supplementary Table 7). Each 40-bp hybridization site was separated by at least 10 bp containing no homology with the mouse transcriptome. Barcodes were ordered from IDT as gBlocks Gene Fragments in tubes and were cloned into the LsgC vectors on the 3′ side of the mCherry using NEBuilder HiFi DNA Assembly. sgRNAs were inserted into their corresponding LsgC-barcode vector by digesting BbsI restriction sites, followed by room-temperature ligation (T4 DNA ligase, NEB) with the annealed forward and reverse sgRNA primers. LsgC barcodes were transformed into DH5α competent cells (Thermo Fisher). The three unique LsgC barcodes were separately transfected into platinum-E (PlatE) cells (Cell Biolabs, no authentication or mycoplasma contamination test) to make retrovirus. One day before the transfections, 2.5 × 105 PlatE cells were plated on 10-cm dishes in PlatE medium (89% DMEM, 9% FBS, 1% HEPES 1 M, 1% penicillin-streptomycin-glutamine (PSG) (100×, Thermo Fisher) and

0.1% 2-mercaptoethanol (BME)). PlatE cells were transfected using a mix containing 10 µg of LsgC-barcode vector, 5 µg of PCL-Eco (Addgene, 12371) and TransIT-LT1 (Mirus). Retrovirus was collected at 48 h and 72 h after transfection and stored at −80 °C until use.

## Methods: Transductions and spatial transcriptomics with pooled perturbations

One day before transduction, splenic P14 CD8 T cells were isolated from a Cas9–eGFP donor mouse through negative enrichment, and plated in T cell medium (TCM) (89% RPMI, 9% FBS, 1% HEPES 1 M, 1% PSG (100×, Thermo Fisher) and 0.1% BME) containing 1:500 anti-CD3e (Fisher Scientific, 50-112-9591) and CD28 (Fisher Scientific, 50-112-9711) on a six-well plate precoated with 1:30 goat anti-hamster IgG (H+L; Thermo Fisher Scientific) in PBS and stored at 37 °C overnight. Furthermore, an untreated six-well plate was coated with 15 µg ml−1 of retronectin (Takara Bio) in PBS and stored in the dark at 4 °C overnight. During transduction, the retronectin was removed and the plates were coated with TCM and incubated at 37 °C for 30 min. After removal, the three treated plates were coated with a corresponding LsgC-barcode retrovirus over two successive 30-min incubations. Activated cells were resuspended in a 1:1,667 IL-2 in TCM mixture and spread equally across the three retronectin-treated plates. Corresponding retroviruses were added to each well, and the plate was centrifuged at 2,000 rpm for 40 min at 37 °C. The sgRNA knockouts were validated by performing flow cytometry on the transduced cells 2 days after transduction using anti-THY1.2 antibody (30-H12, BioLegend, 1:200 dilution) and anti-CXCR3 antibody (CXCR3-173, eBiosciences, 1:200 dilution) with mCherry+ anti-CD8a+ (53-6.7 BioLegend, 1:200 dilution) cells gated as successfully transduced. One day after transduction, mCherry GFP+ cells were sorted from each of the three transduced populations and pooled 1:1:1, then 1 × 105 cells were transferred into each recipient mouse. Recipient mice were immediately infected with LCMV and euthanized at 7 d.p.i. for spatial transcriptomics.

## Methods: Computational analysis of pooled perturbations in spatial transcriptomics

To stringently identify perturbed CD8 T cells in the spatial transcriptomics datasets, we identified all cells for which the sum of raw transcripts for Cd8a, Cd8b1 and Cd3e was greater than or equal to 3, that had at least one barcode detected, that belonged to a CD8 T cell cluster and that had ≤1Muc2 transcript.Fer1l6, the pseudogene for sgCXCR3, shows low expression in goblet cells, requiring a stringent filtering of Muc2 to minimize the possibility of goblet transcript bleed-over falsely marking a CD8 T cell as perturbed.

###### b

###### a

+LCMV P14 CD8 T cells

Time pi (day)

Small Intestine roll embedding (proximal)

Small Intestine Small Intestine

IF

snRNAseq (2591 genes) snRNAseq (Xenium 350 genes)

56 60

7 30

120

1 d

|![image 10053](s41586-024-08466-x_images/imageFile10053.png)<br><br>ARI: 0.87 AMI: 0.88| |
|---|---|
|![image 10053](s41586-024-08466-x_images/imageFile10053.png)<br><br>ARI: 0.87 AMI: 0.88| |


|PERSIST (180) NicheNet (158) Immgen (21) Xist (1)|PERSIST (180) NicheNet (158) Immgen (21) Xist (1)|
|---|---|
|10X| |


|![image 10054](s41586-024-08466-x_images/imageFile10054.png)<br><br>ARI: 0.72 AMI: 0.76|


effector memory

Immunofluorescence Object classifier

P14 Epithelia

CD45.1 E-cadherin


Villi

|FPKM thresholds Gene constraints|


Crypt Muscularis

- f B cell DC Eosinophil Myeloid NK ILC MAIT Monocyte T Cell

6 8 30 90 6 8 30 90 6 8 30 90 6 8 30 90 6 8 30 90 6 8 30 90 6 8 30 90 6 8 30 90 6 8 30 90

3.5 3.0 2.5 2.0 1.5 1.0 0.5

1.2

0 0

1.0 0.8 0.6 0.4 0.2

0

0.05

0.10

0.15

Time p.i. (day)

2.0

- 0

0.5

1.0

- 1.5 1.2


- 0
- 1.0 0.8 0.6 0.4


0.2

1.4

- 3

- 0
- 1
- 2


- 4


3 2.5

2 1.5

1 0.5

0

2.5 2.0 1.5 1.0 0.5

0 0

2.5

5.0

7.5

10.0

12.5

15.0

Cell Frequency (%)

d

6 8 30 90

Time p.i. (day)

102 103 104 105 106

- 102
- 103
- 104
- 105
- 106


|r=0.93|


|r=0.95|


|r=0.95|


|r=0.97|


Total counts replica 2

Total counts replica 1

- 102
- 103
- 104
- 105
- 106


- 102
- 103
- 104
- 105
- 106


- 102
- 103
- 104
- 105
- 106


102 103 104 105 106 102 103 104 105 106 102 103 104 105 106

|AMI ARI<br><br>350 genes<br><br>AMI: 0.88 ARI: 0.86<br><br>AMI: 0.85 ARI: 0.83<br><br>1000 genes|


Accuracy Metrics

0

400 800 1200

0.2

0.4

0.6

0.8

1.0

0

Number of Genes

c

e


Xist Cd8a Cd3e Clec9a Xcr1

Xist Cd8a Cd3e Pecam1

Xist Cd8a Cd3e Acta2

Xist Cd8a Cd3e Lyve1

Xist Cd8a Cd3e Rbfox3

P14 and cDC1 P14 and Endothelial P14 and Fibroblast P14 and Lymphatics CD8a and Neuron

- g P14 CD8 T Cells

U 6 8 27 U 6 8 27 U 6 8 27

- 103
- 104
- 105
- 106
- 107
- 108


Cell Count

- 103
- 104
- 105
- 106
- 107
- 108


CD8αβ T Cells

U 6 8 27 U 6 8 27 U 6 8 27

- 103
- 104
- 105
- 106
- 107


CD8αα T Cells

U 6 8 27 U 6 8 27 U 6 8 27 B Cells (B220 Positive)

- 105
- 106
- 107
- 108

- 109


U 6 8 27 U 6 8 27 U 6 8 27

Monocytes

U 6 8 27 U 6 8 27 U 6 8 27 Time p.i. (day)

- 101
- 102
- 103
- 104
- 105
- 106
- 107


CD4 T Cells

U 6 8 27 U 6 8 27 U 6 8 27 γδT Cells

- 103
- 104
- 105
- 106
- 107
- 108


- 103
- 104
- 105
- 106
- 107


U 6 8 27 U 6 8 27 U 6 8 27

Time p.i. (day)

- 102
- 103
- 104
- 105
- 106
- 107


DC

U 6 8 27 U 6 8 27 U 6 8 27

Spleen SI IEL SI LPL

Time p.i. (day)

Cell Count

***

***

***

***

***

***

***

***

***

***

**

**

***

*

*

***

**

***

*** ***

*

*

****

****

0.006

−1.0

−0.5

0.0

0.5

1.0

Spleen

IEL

log(female/male)2

Spleen IEL

CD103− CD69−

CD103− CD69+

CD103+ CD69+

CD103− CD69−

CD103− CD69+

CD103+ CD69+

0

25

50

75

100

subset (%)


female male

female CD45.1 P14

0

male CD45.2

1:1 mix

+LCMV

Collect tissues

30 d p.i.

male CD45.1/2 P14

i j k

1.0

0

0.8 0.6 0.4 0.2

Xist

expression

P14 CD8 T cells

6 8 30 90 Time p.i. (day)

- h


Time p.i. (day)

***

Extended Data Fig. 1 |See next page for caption.

- Extended Data Fig. 1 | Related to Fig. 1. Targeted detection of LCMVspecific CD8 T cell responses in the mouse small intestine with spatial transcriptomics.a, Schematic of the experimental workflow for mouse takedown at progressing timepoints post infection (p.i.) with LCMV. An object classifier in QuPath is used to identify P14 and epithelial cells from IF staining of intestinal sections. (1 representative field of view out of n > 20 similar)


- b, Diagram of the methodology used to design the Xenium mouse SI probe panel. Using snRNA-seq data from the mouse small intestine, a 350 gene set was designed to maximize Adjusted Rand Index (ARI) and Adjusted Mutual Information (AMI) scores of classifier-derived Leiden cluster predictions.
- c, Genes least informative for predicting cell type are continuously pruned using recursive feature elimination with ARI and AMI of classifier-derived Leiden cluster predictions calculated at each pruning step.d, Pearson residual correlations of total gene abundances between timepoint biological replicates.e, Snapshots from a Xenium spatial transcriptomics day 6 small intestine show unique cell types in close spatial proximity. Canonical cell type marker gene transcript positions are colored to show a (from left to right) P14 T Cell (Xist+Cd8α+Cd3e+) and cDC1 (Clec9a+Xcr1+), P14 T Cell and Endothelial (Pecam1+), P14 T Cell and Fibroblast (Acta2+), P14 T Cell and Lymphatic (Lyve1+),


and Cd8α T Cell (Cd8α+Cd3e+) and Neuron (Rbfox3+). Predicted cell segmentation boundaries are colored by the “Type” annotation.f, Cell type frequency percentages across n = 2 replicates per timepoint.g, Absolute cell numbers quantified by flow cytometry for the indicated cell types and time points after LCMV infection (n = 5). Two-way ANOVA with Dunnett’s method. Bars indicate the mean +/- SEM. ***p-value < 0.001.h,Xist expression within detected P14 CD8 T cells (Xist+) at each time point (n = 13000,n = 8412,n = 1155,n = 433 cells in 6 dpi, 8 dpi, 30 dpi, and 90 dpi respectively across 2 biological replicates per time point). Pairwise t-tests on the mean expression values with BenjaminiHochberg correction applied ***p-value < 0.001.i, Experimental design for a female:male P14 CD8 T cell transfer in B6 mice.j, Relative frequencies of female to male ratios in the indicated tissues 30 days p.i. Unpaired two-sided t-test with Tukey’s HSD, *p-value < 0.05. Data are presented as the mean +/− Tukey’s HSD confidence interval.k, Frequency of P14 CD8 T cells by sex and CD103 and CD69 expression analyzed by flow cytometry in the indicated tissues 30 days p.i. Unpaired t-test with Tukey’s HSD. No significant p-values detected. Data are presented as the mean +/− Tukey’s HSD confidence interval. 2 independent biological duplicates of n = 3 and n = 5 specimens are pooled (j andk). Panelsa andi reproduced from ref. 5.


- Extended Data Fig. 2 | Related to Fig. 2. Spatial framework of the mouse intestinal villus shows cell positioning dynamics over time after an LCMV infection. IMAPs of all cell subtypes from each time point (two biological


replicates for each time point combined), with colored gates dividing the top IE, top LP, crypt IE, crypt LP, and muscularis.


- Extended Data Fig. 3 | Related to Fig. 2. Spatial transcriptional patterning of mouse intestinal cells over the course of an LCMV infection revealed by spatial transcriptomics.a, Frequency of P14 CD8 T cells present in binned segments of equal length of the longitudinal axis for n = 2 replicates per time point.b, Heatmap depicting the percentage of genes in every cell subtype correlated with each axis using all combined time course samples (n = 8). Heatmap colors indicate for all genes expressed in a particular cell type, few of them correlate with the corresponding axis (white), or most of them correlate with the corresponding axis (dark red).c, UCell enrichment of epithelial zonation signatures22 in epithelial cells from pooled Xenium replicates ordered by crypt-villus axis position. Signatures are the top 30 differentially expressed, overlapping genes per zone.d, UCell enrichment


of proximal and distal epithelial signatures15 in epithelial cells from each Xenium replicate, binned and ordered by longitudinal position. Zwick signatures include all overlapping genes with Spearman’s ρ > 0.5 between expression and longitudinal segment order.e, IF staining of CD8α, TCF1 and GZMB of a mouse intestine 30 days after LCMV infection. Representative picture of 3 independent samples. Scale bars are 2 µm.f, Gene expression of indicated genes for P14 CD8 T cells grouped by the spatial gates shown in Fig. 2d over time; n = 2 replicates per time point.g, Gene expression of indicated genes for intestinal P14 CD8 T cells over time after an LCMV infection profiled by scRNA-seq.h, IMAPs of day 90 P14 CD8 T cells (one of two biological replicates) colored by Blimp1high differentiated and Id3high progenitor-like TRM signatures enrichment derived from Milner et al.


- Extended Data Fig. 4 | Related to Fig. 3. Immune response to LCMV profiled by whole-transcriptome spatial sequencing of the mouse small intestine. a, VisiumHD results on mouse small intestine roll 8 days after LCMV infection colored by graph-based clustering.b, VisiumHD spots colored by imputed crypt-villus axis values.c, Ratios of overlapping gene expression at the top vs. bottom in epithelial cells from day 8 pi Xenium and VisiumHD dataset. r: Pearson correlation coefficient.d, Convolved gene expression of cytokines


along the imputed crypt-villus axis in the VisiumHD dataset. Red labels indicate genes that were included in the Xenium gene panel.e, Transcript reassigning based on H&E nuclei segmentation to achieve single-nuclei level gene expression data (left) and example (right).Reg3b is plotted to showcase the single-nuclei level data.f, Incoming signals across CD8αβ regional subtypes in the VisiumHD dataset.


- Extended Data Fig. 5 | Related to Fig. 3. Spatial immune landscapes of the healthy mouse small intestine.a, Pearson residual correlations of total gene abundances between biological replicates of an uninfected mouse intestine profiled by Xenium.b, Convolved gene expression by all cells along the cryptvillus and epithelial axes. 2 biological replicates combined. c, Cell type


interaction igraph of the uninfected mouse small intestine. 2 biological replicates combined.d, IMAP of CD8αβ T cells in the uninfected small intestine. 2 biological replicates combined.e, expression IMAP for indicated genes in the uninfected intestine. 2 biological replicates combined.f, Convolved gene expression within uninfected CD8αβ T cells along the crypt-villus axis.


###### a b

Megakaryocyte/Platelet Monocyte

αβCD8 T Cell Complement Fibroblast

sgCd19

Tuft Vascular Endothelial

Fibroblast FibroblastNCam1+

Resting Fibroblast T Cell

- FibroblastPdgfra+
- FibroblastPdgfrb+


Enteroendocrine Eosinophil

DC2 Early Enterocyte

P14 CD8 T Cell ααCD8 T Cell

Myofibroblast NK Cell

sgCxcr3

- Enterocyte 1
- Enterocyte 2
- Enterocyte 3


MAIT Macrophage

B Cell CD4 T Cell

fraction of cells in group

ISC Lymphatic

γδT Cell TA

Neuron Paneth

0 104 105 CXCR3-APC

Goblet ILC

cDC1

20 40 60 80

Mean expression in group

Fer1l6 Neurog3 Muc5ac

sgCd19


0 1

combined timecourse samples (d6, d8, d30, d90 p.i. LCMV)

sgThy1

###### d

fraction of cells in group

0 104 105 Thy1-BV510

other cells

pseudo-Muc5ac sgCd19

pseudo-Fer1l6 sgCxcr3

pseudo-Neurog3 sgThy1

c

###### e

sgCd19 sgCxcr3

20 40 60 80 Mean expression in group

P14 CD8 * T cells

4 3 2 1 0

|3661<br><br>61 1 1.64% 0.03%<br><br>98.3%|


3 2 1 0

4000

4 3 2 1 0

pseudogene

Count

expression

3000

barcode

sgThy1

2000

|![image 10069](s41586-024-08466-x_images/imageFile10069.png)|![image 10069](s41586-024-08466-x_images/imageFile10069.png)|
|---|---|
| | |


1000 0

pseudo-Neurog3

pseudo-Muc5ac

pseudo-Fer1l6

musc.

musc.

musc.

1 2 3 unique sgRNA number/cell

LP IE LP IE

LP IE LP IE

LP IE LP IE

crypt top

crypt top

crypt top

- Extended Data Fig. 8 | Related to Fig. 4. Optical readout of sgRNA-containing antigen-specific CD8 T cells in the mouse intestine integrated in the Xenium assay.a, Flow cytometry histograms showing quantification of Thy1 and CXCR3 of Cas9eGFP P14 CD8 T cells transduced with Thy1 and Cxcr3-targeting sgRNAs. Representative of two independent biological replicates.b, Dot plot gene expression of the three least expressed genes in the 350 gene panel for all cells in the small intestine, all time points and replicates (n = 8) combined.c, Frequency of


CD8 T cells containing one, two or three different sgRNAs. 2 biological duplicates combined.d, Expression of pseudo-gene barcodes in the perturbed day 8 small intestine.e, Capture of pseudo-gene barcodes along the spatial areas of the small intestine defined by IMAP for each perturbation. Two-sample t-test of the mean expression levels, with Benjamini-Hochberg correction applied, *p-value < 0.05. Sample sizes shown in Supplemental Table 12.

###### a b

Terminal Ileum #1 R1 R2

322 human Colon pre-designed (10X)

R1 R2


DEG from Xenium mouse study n=26

|Boland et al scRNAseq dataset T Cells and DCs|Boland et al scRNAseq dataset T Cells and DCs|
|---|---|
| | |


Priors

Terminal Ileum #2

R1 R2

R1 R2

PERSIST


Feature Selection

Preliminary human gene panel

Refinement

422 gene panel

###### d

###### c

## Methods: Cell Type

Terminal Ileum #1 Terminal Ileum #2 105 104 103 102

Fraction of cells in group (%)

PP CD8ab T Cell PP CD8ab T Cell PP CD4 T Cell PP T Cell PP T Cell PP T Cell PP T Cell PP T Cell PP CD4 T Cell PP CD8ab T Cell GZMK+

2.0 2.1 2.2 2.3 2.4 2.5 2.6 2.7 2.8 2.9

|r=1.00|


|r=1.00|


Expression counts R1

105 104 103 102

20 40 60 80100

Mean expression in group


0 2 4

PP CD8ab T Cell Proliferating

2.10 2.11 2.12 2.13 2.14 2.15

102 103 104 105 102 103 104 105

PP T Cell PP T Cell PP T Cell PP CD8ab T Cell PP CD8ab T Cell

Expression counts R2

Sub leiden category

- e
- f


Effector T Cell CD8 GZMK+ Effector

CD8 T Cell

1.0 0.8 0.6 0.4 0.2


3.0 3.1 3.2 3.3 3.4 3.5 3.6 3.7 3.8 3.9

CD8 T Cell CD8 GZMK+ Effector

CD4 CD4 CD4 CD4


Crypt-Villus axis

Effector T Cell Effector T Cell gd T Cell

0

0.15 0.3 0.6 1 6

0.150.3 0.61 6 0.150.3 0.61 6

T Cell GZMK++ ITGAE++ Treg Other_11 Proliferating T Cell Other_13

Proliferating T Cell T Cell GZMK+ ITGAE+ gd T Cell

3.10 3.11 3.12 3.13

| || |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|
|---|---|---|---|---|---|---|
| || |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|
| || |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|
| || |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|
| || |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|
| || |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|| |
<br><br>| |
<br><br>| |
<br><br>| |
|
| | | | | | | |


1.0 0.8 0.6 0.4 0.2


- CD8A
- CD8B


SELL

KLRG1

FOXP3

CD3D

CD3G

TRBC1

CD4

GZMB

IL2RB

IL7R

TRAC

CCL5

TCF7

MKI67

ITGAE

CD3E

MAF

GZMK


g

Top Bottom

Gene Expression differences in CD8AB T Cells Top vs Bottom LP vs IEL

0

.15 .3 .6 16 0.15 0.3 0.6 1 6 0.15 0.3 0.6 16

120 100

|TCF7<br><br>ITGAE<br><br>GZMA<br><br>|


|ITGAE<br><br>TCF7 GZMA<br><br>|


Epithelial axis

140 120 100

(Corrected p-values)

Other DC

80 60 40 20 10

Mast

-Log100

80 60 40 20 10

cDC1 Monocyte Conventional

Lymphatic Plasma Cell

DC

PP CD4 T Cell

Macrophage

PP CD8ab Prolif.

Effector T Cell

Vascular Endo. AQP+

0 Corrected p-value < 0.05

-3 -2 -1 1 2 3 4 -3 -2 -1 0 1 2

Fibroblast

CD4

Log2 Fold Change

Vascular Endo. CPE+

h

PP CD8ab T Cell

Proliferating Myeloid

| | | | | | | | | | | | | | | | | | | | | | | | |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | | | | | | | | | | | | |
| | | | | | | | | | | | | | | | | | | | | | | | |
| | | | | | | | | | | | | | | | | | | | | | | | |
| | | | | | | | | | | | | | | | | | | | | | | | |
| | | | | | | | | | | | | | | | | | | | | | | | |
| | | | | | | | | | | | | | | | | | | | | | | | |
| | | | | | | | | | | | | | | | | | | | | | | | |


B Cell

- TGFBR1
- TGFBR2


Vascular Endo.

Other Myeloid

ITGAV

Other T Cell #13

- TGFB1
- TGFB2
- TGFB3


CD8 T Cell

Neuron

## Methods: Proliferating T Cell

PP CD8ab T Cell GZMK+

Enterocyte

gdT Cell

Fraction of cells in group (%)

B Cell

## Methods: Enterocytes

Fibroblast

Goblet

Lymphatic

Mast

Other DC

Paneth

Other T cell

Conventional DCs

Endothelial

Enteroendocrine

Monocyte

Neuron

Macrophage

Myeloid

CD8 GZMK+ Eff

Other T Cell #11

Enteroendocrine

Goblet

20 40 60 80 Mean expression in group

## Methods: gd T Cell

Tuft

T Cell GZMK+ ITGAE+

TA


+ +

Paneth

1 2

- Extended Data Fig. 9 |See next page for caption.


Extended Data Fig. 9 | Related to Fig. 5. Immune landscape of the human small intestine revealed by spatial transcriptomics.a, Schematic for designing the Xenium human SI gene panel. The Xenium base human colon panel was expanded with canonical immune genes, the human homologs of top spatially differentially expressed genes from the Xenium mouse data, and computationally derived genes that best capture the heterogeneity within immune cell types found in scRNA-seq data from Boland et al.b, Xenium processed terminal ileum samples divided into two rows corresponding to the two human donors. Adjacent tissue sections were taken from both donors and are positioned side-by-side within the joint MDE embedding (left) and spatially (right). Cells are colored by their annotations in Fig. 5a.c, Scattered raw gene expression abundances between the technical replicates of both human ileums overlayed with a line of best fit. The Pearson residual correlation coefficient (r) is calculated between the gene abundances of both samples.d, Expression of genes used to annotate immune subtypes. Colors of dots indicate the mean expression of the gene in each subcluster, and size of the dots correspond to the percentage of cells in each subcluster expressing the gene. The final cell subtype

annotations of each subcluster are shown as y-ticks along the right side of the plot.e, IMAP positioning of select T-Cell subtypes within all (n = 4) human sections (Peyer’s Patches excluded). Cells are colored by kernel density estimates of their coordinate location within the IMAP. IMAP gates are positioned as in Fig. 5d.f, Aggregated physical interaction network where edges between nodes represent a normalized Squidpy interaction score lying above a 0.1 threshold (10% of the connections). Nodes are positioned using a Kamada-Kawai layout algorithm on the averaged interaction matrix of all human sections.g, Differential expression testing of all genes expressed in at least 5% of human CD8αβ T Cells using diffxpy. A two-tailed Wald test yielded a fold change and adjusted p-value (padj) for each gene (X) between human CD8αβ T cells gated in the crypt versus those gated in the top of the villus, and (X) human CD8αβ T cells gated intraepithelial versus those gated in the lamina propria. All genes are plotted by their log2 fold change and -log100(padj), and significantly differentially expressed genes (padj <0.05) are colored red. h, Expression of TGFβ isoforms and genes involved in TGFβ presentation across cell types after pooling the cells from all human sections (n = 4).


Corresponding author(s): Goldrath, Heeg Last updated by author(s): 11/01/2024
