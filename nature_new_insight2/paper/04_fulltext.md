# Full Text — # Tissue-resident memory CD8 T cell diversity is spatiotemporally imprinted

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

# Tissue-resident memory CD8 T cell diversity is spatiotemporally imprinted

Miguel Reina-Campos1,2,7, Alexander Monell1,3,7, Amir Ferry1, Vida Luna1, Kitty P. Cheung1, Giovanni Galletti1, Nicole E. Scharping1, Kennidy K. Takehara1, Sara Quon1, Peter P. Challita1, Brigid Boland4, Yun Hsuan Lin4, William H. Wong4, Cynthia S. Indralingam4, Hayley Neadeau2, Suzie Alarcón2, Gene W. Yeo3, John T. Chang4,5, Maximilian Heeg1,6,7✉ & Ananda W. Goldrath1,6✉

https://doi.org/10.1038/s41586-024-08466-x Received: 29 February 2024 Accepted: 27 November 2024 Published online: 22 January 2025 Open access

Tissue-resident memory CD8 T (TRM) cells provide protection from infection at barrier sites. In the small intestine, TRM cells are found in at least two distinct subpopulations: one with higher expression of effector molecules and another with greater memory potential1. However, the origins of this diversity remain unknown. Here we proposed that distinct tissue niches drive the phenotypic heterogeneity of TRM cells. To test this, we leveraged spatial transcriptomics of human samples, a mouse model of acute systemic viral infection and a newly established strategy for pooled optically encoded gene perturbations to profile the locations, interactions and transcriptomes of pathogen-specific TRM cell differentiation at single-transcript resolution. We developed computational approaches to capture cellular locations along three anatomical axes of the small intestine and to visualize the spatiotemporal distribution of cell types and gene expression. Our study reveals that the regionalized signalling of the intestinal architecture supports two distinct TRM cell states: differentiated TRM cells and progenitor-like TRM cells, located in the upper villus and lower villus, respectively. This diversity is mediated by distinct ligand–receptor activities, cytokine gradients and specialized cellular contacts. Blocking TGFβ or CXCL9 and CXCL10 sensing by antigen-specific CD8 T cells revealed a model consistent with anatomically delineated, early fate specification. Ultimately, our framework for the study of tissue immune networks reveals that T cell location and functional state are fundamentally intertwined.


TRM cells have a pivotal role in the adaptive immune response, offering localized, long-term protection in non-lymphoid tissues through con-

fine granularity needed to capture different CD8 T cell transcriptional states and the variety of the non-immune cellular phenotypes that surround them, which requires highly multiplexed subcellular-resolution imaging technologies. Spatial transcriptomics enables the profiling of hundreds of different mRNA molecules simultaneously in cells across complete tissue sections, in combination with protein and histology read-outs. Here, we exploit spatial transcriptomics and develop a computational framework to characterize the cellular and ligand–receptor interactions that guide intestinal TRM cell differentiation. We further show the feasibility of a multiplexed, optically encoded spatial CRISPR knockout experiment in an in vivo setting to explore cytokine gradients during immune cell differentiation and expand our models of T cell differentiation in the SI.

tinuous tissue surveillance2. TRMcell formation requires the engagement of transcriptional and metabolic programs that induce tissue-specific adaptations3–6. These programs, initiated by priming events in lymphoid tissues7, are reinforced by cellular interactions and the sensing of environmental factors on tissue entry8,9, such as TGFβ10,11, which enhances the upregulation of retention molecules including CD103 (encoded byItgae) in epithelial barriers such as the small intestine (SI)10. Recent studies have shown that intestinal TRM cells exhibit functional heterogeneity, with at least two distinct states identified in response to acute infections in the SI: a more terminally differentiated TRM cell population and a progenitor-like one1,4,12,13. These subpopulations display distinct cytokine production and secondary memory potential, highlighting the nuanced nature of the development and function of TRM cells in tissues to provide long-term immunity. In fact, recent investigations into the architectural structure of the mouse and human SI have uncovered spatially organized transcriptional and metabolic programs that establish complex intestine regionalization14–16. How these tissue microenvironments affect TRMcell differentiation and function has not been previously addressed. This is in part because of the

###### A spatial framework for SI TRMcells

To quantitatively and systematically capture the spatial distribution of antigen-specific CD8 T cells in the SI responding to lymphocytic choriomeningitis virus (LCMV) infection, we used T cell receptor transgenic CD8 T cells (P14 CD8 T cells), which specifically recognize the LCMV glycoprotein 33–41 peptide presented by H2-Db. After adoptive transfer


of P14 CD8 T cells from mice with a CD45.1 congenic background into CD45.2 wild-type mice and LCMV infection, SIs were collected at different timepoints to analyse the number and intratissue location of transferred cells (Extended Data Fig. 1a). To obtain an unbiased assessment of cell location in the tissue, we implemented a dual-coordinate-axis system based on the proximity of individual P14 CD8 T cells, detected by histological staining of CD45.1 and CD8α, to the nearest epithelial cell or the distance to the base of the muscularis (Fig. 1a and Extended

- Data Fig. 1a). This approach creates a two-dimensional density representation of the overall distribution of P14 CD8 T cells in the villus, the repetitive functional structure of the SI, which we termed immune allocation plot (IMAP) (Fig. 1a). IMAPs generated over the course of an LCMV infection captured the distribution dynamics of P14 CD8 T cells in the SI, revealing infiltration of the muscularis at an effector timepoint, followed by rapid clearance and a subsequent formation of two spatially separated populations along the crypt–villus axis (Fig. 1b). These data suggest that P14 CD8 T cells dynamically occupy different regions in the SI after infection.

To study the relationship between the gene-expression programs and locations of TRM cells, we adoptively transferred female P14 CD8 T cells to male mice, infected them with LCMV and performed spatial transcriptomic profiling (Xenium, 10x Genomics)17,18 on mouse SIs over the course of the LCMV infection (6, 8, 30 and 90 days post infection (d.p.i.)). A 350-plex target gene panel was designed using a reference single-nucleus RNA sequencing (RNA-seq) dataset to inform a prioritization algorithm based on predictive deep learning19 (Extended Data Fig. 1b). Furthermore, we included probes to detect relevant immune gene markers curated from the ImmGen database20, ligand–receptor pairs21 andXist, a long non-coding RNA exclusively expressed in female cells that was used to track P14 CD8 T cells in the male hosts (Extended

- Data Fig. 1b). Recursive feature-elimination modelling showed that 350 genes captured the biological heterogeneity found in the SI using single-nucleus RNA-seq (Extended Data Fig. 1c and Supplementary Table 1). After Xenium processing, tissues were further analysed by immunohistochemical detection of CD8α and cellular membranes with wheat germ agglutinin (WGA), as well as haematoxylin and eosin (H&E) staining, which enabled the assessment of overall tissue structures (Fig. 1c). This analysis provided in situ measurements of 350 genes on 1.8 million cells over four timepoints, with highly correlated biological duplicates (r ≥ 0.93), capturing an average median count of 98 transcripts per cell and enabling the identification of 36 distinct cell types, including P14 CD8 T cells (CD8α+andCd8a+Cd8b+Xist+) (Fig. 1c,d, Extended Data Fig. 1d–f and Supplementary Table 2). As expected with the course of infection, endogenous CD8αβ T cell and P14 CD8 T cell fractions were the most changed after LCMV infection with a notable increase in B cell frequencies (Fig. 1d and Extended Data Fig. 1f). Similar dynamics were observed by flow cytometry analysis (Extended Data Fig. 1g and Supplementary Fig. 1). Xist expression was successfully detected in P14 CD8 T cells across timepoints (Extended Data Fig. 1h),


and female CD8 T cells were able to differentiate effectively into SI TRM cells in a male host, as shown by a mixed female:male transfer in the context of LCMV infection (Extended Data Fig. 1j,k). Notably, spatial visualization of phenotypic diversity by Leiden clustering revealed a marked spatial pattern (Fig. 1d), suggesting that our approach was able to capture transcriptional regionalization while simultaneously being able to capture a broad range of cell types in the SI.

###### SI TRMcell diversity is spatially defined

To study the transcriptional programs of SI TRM cells as a function of their unique location in the tissue, we generated IMAP representations for each cell type (Extended Data Fig. 2) by calculating coordinates along three main axes of reference for every cell: distance to the muscularis (crypt–villus axis) (Fig. 2a), distance along the gastrointestinal tract (longitudinal axis) (Fig. 2b) and distance to the nearest epithelial

cell (epithelial axis) (Fig. 2c). IMAPs for P14 CD8 T cells across the infection time course revealed a dynamic shift in their location over time, from a relative accumulation in the lower villus and muscularis at 6 d.p.i. to forming two spatially resolved populations along the crypt–villus axis by 90 d.p.i. (Fig. 2d). P14 CD8 T cells were uniformly distributed along the longitudinal axis over time (Extended Data Fig. 3a). We next considered whether the cellular distribution had an effect on P14 CD8 T gene expression programs. Out of the 191 genes detected in P14 CD8 T cells (expressed in more than 5% of these cells), 87 genes (46%) had notable changes in expression along the crypt–villus axis, 76 genes (40%) changed along the epithelial axis and 8 genes (4%) changed along the longitudinal axis (Fig. 2e). These results indicated strong transcriptional imprinting based on the intratissue location of P14 CD8 T cells, influenced primarily by the crypt–villus and epithelial axes. Other immune cells displayed similar correlations with variable expression along the epithelial and crypt–villus axes, as well as epithelial cells, which followed expression gradients consistent with previous studies14–16,22 (Extended Data Fig. 3b–d and Supplementary Table 3). In P14 CD8 T cells, genes associated with progenitor-like TRM cells,Tcf7 andSlamf6, and short-lived effectors (Il18r1 andKlrg1), were expressed in the lower villus area, whereas genes associated with differentiated TRM cells, such asItgae,Gzma andGzmb, were highly expressed around the top of the villus (Fig. 2f–h). Consistently, CD8α+TCF1+ cells were found predominantly in the crypt and lower villus area whereas CD8α+ GZMB+ cells were found predominantly in the top intraepithelial side of the villus as revealed by immunostaining (Extended Data Fig. 3e). Transcriptional gradients were also apparent along the epithelial axis, with progenitor-like TRM-cell- and short-lived effector-cell-associated genes preferentially expressed by P14 CD8 T cells in the lamina propria

- (Fig. 2i). At the population level,Gzma andGzmb expression decreased concomitantly with an increase inTcf7 expression over time (Extended

- Data Fig. 3f), as previously shown by single-cell RNA-seq1,12 (Extended
- Data Fig. 3g). Despite these overall changes at the population level over time, the gene-expression polarization along the crypt–villus axis was evident at each individual timepoint (Fig. 2f–i). To put our results in the context of our previous observations, the projection of gene signatures


for progenitor-like TRMcells and more differentiated TRMcells (clusters 3 and 29, respectively12) into the spatial coordinates of P14 CD8 T cells

at 90 d.p.i. delineated a population of TRM cells expressing cluster 3 genes preferentially located near the bottom of the villus, and TRM cells enriched for expression of cluster 29 located at the top of the villus

- (Fig. 2j). Similar results were obtained using signatures derived from


long-lived ID3+ TRM cells and shorter-lived effector BLIMP1 TRM cells1 (Extended Data Fig. 3h). Together, these data show that the phenotypic and gene-expression heterogeneity of SI CD8 T cells depends largely on their location in the tissue.

###### Regionalized intestinal immune signalling

To understand better how the anatomical position in the SI leads to TRM cell heterogeneity, we focused on the composition of the cellular communities around P14 CD8 T cells over time (Fig. 3a). A graphic representation of the cellular connectome of the SI separated four spatial domains: immune (lamina propria), epithelial, muscularis and crypt regions (Fig. 3b). At effector timepoints (6 and 8 d.p.i.), P14 CD8 T cells interacted mostly with immune cells of the lamina propria and fibroblasts, whereas connections with immune cells of the upper villus and enterocytes dominated at later memory timepoints (Fig. 3b), consistent with their location (Fig. 2d). P14 CD8 T cells nearer to the tip of the villus (enriched for expression of cytotoxic molecules) were in closer proximity to enterocytes, and immune cells preferentially located in the top intraepithelial area, such as mucosal-associated invariant T cells and natural killer cells, whereas P14 CD8 T cells nearer to the crypts (enriched for expression of progenitor-like genes) had increased physical proximity to B cells, CD4 T cells, fibroblasts and progenitor


a

V

C M

|y  x  |


Top

Crypt–villus axis (m)

IEL

Villus

LPL

IEL LPL

Crypt Muscularis

Bottom

Distance to nearest epithelial cell ( m)

b

Top Crypt Muscularis

5

Time (d.p.i.):

6

7

Crypt–villus axis (m)

600 400 200

600 400 200

600 400 200

0

0

0

0 20 40 60

0 20 40 60

0 20 40 60

Distance to nearest epithelial cell ( m)

600 400 200

0

60

0 20 40 60

- c


d

Time (d.p.i.): 6 8 30 90


|T cell|


|T cell|


|T cell|


|T cell|


P14Main cell typesLeiden clusteringSI rollMDE

H&E

IF

CD8 WGA


Leiden


|


Xist

Gzmb


- Cd8a


CD8 WGA

Fibroblast ILC

B cell DC

MAIT Monocyte

Endothelial Eosinophil

Myeloid NK

Epithelial absorptive Epithelial progenitor

Neuron T cell

Epithelial secretory Erythroid

All transcripts

- Fig. 1 | Characterization of the spatial and transcriptional state of antigen-specific CD8 T cells in response to acute viral infection in the mouse SI with spatial transcriptomics.a, Left, a coordinate system to define morphological axes in the SI. C, crypt; M, muscularis; V, villus. Right, the distance to the nearest epithelial cells and the distance to muscularis form the basis of an IMAP. The top of the villus and the crypt regions house both intraepithelial lymphocytes (IEL) and lamina propria lymphocytes (LPL).b, An IMAP representation of P14 T cell localization measured by immunofluorescence (staining at the indicated days after infection. Two biological replicates forn= 3 mice per timepoint, representative data from one mouse are shown. The gates for the top of the villus (blue), the crypt (red) and the muscularis (beige) highlight the different regions. The points, representing cell positions, are coloured by kernel density estimates over the IMAP (x, y) coordinates.c, An overview of the Xenium-based spatial transcriptomics data structure: row 1, Xenium output of a mouse intestine (8 d.p.i.), with cells coloured by Leiden cluster;


row 2, a magnification of a villus showing H&E staining; row 3, confocal immunofluorescence images of CD8α and WGA; row 4, Xenium DAPI staining with cell boundary segmentation masks coloured by Leiden cluster; row 5, a further subregion magnification of the same villus depicting Xenium DAPI staining overlaid by cell boundary segmentation and all transcripts assigned to cells (left) and an immunofluorescence image of CD8α and WGA overlaid with transcript locations forCd8a,Cd8b,Gzmband female P14-specificXisttranscript locations overlaid (right).d, An overview of the processed Xenium data of mouse SI at 6, 8, 30 and 90 d.p.i. (columns): row 1, cells in a joint minimum distortion embedding (MDE) of all SI Xenium samples coloured by cell type; row 2, in situ spatial positioning of the cells; rows 3–5, magnifications coloured by cell type (row 3), with P14 clusters/cells highlighted in red (row 4) and coloured by Leiden cluster (row 5). One of two biological replicates for each timepoint is shown. DC, dendritic cell; ILC, innate lymphoid cell; MAIT, mucosal-associated invariant T; NK, natural killer cell.

a

###### b c

Longitudinal axis Epithelial axis

Crypt–villus axis


6

6

6

8

8

8

Time (d.p.i.)

Time (d.p.i.)

Time (d.p.i.)

30

30

30

90

90

90

Bottom Top

Proximal LP

Distal IE

d

e

n = 32

n = 31

n = 7

Top Crypt Muscularis

0.4

6 8 30 90

Time (d.p.i.):

- 101


Higher in tip Higher in LP Higher in dist.

1.0

0.3

Crypt–villus axis

Number of

0.8

P14 cells

0.2

Itgae

Tcf7

0.6

Mxd1

Spearman

0.1

Tcf7

Ctla4

Il7r

0.4

0

0.2

Gzmb Slamf6 Cd69 Tgfbr2 Klrg1 Il18r1 Klf2

Il21r Chn2 Mxd1 Gzmb Itgae Cdh1

0

- –0.3


6 8 30 90

0.150.30.610.156 0.30.6160.150.30.6160.150.30.616

Time (d.p.i.)

Epithelial axis

Expression

###### f

n = 56

n = 44

n = 1

Min. Max.

Crypt–villus Epithelial Longitudinal


Time (d.p.i.): 6 8 30 90

- g


Tcf7

Gzma Gzmb Itgae

Tcf7 Il18r1 Ifng Slamf6 Klrg1

Tcf7 Il18r1


Il18r1 Klf2

1.0

Tcf7 Il18r1

Ifng

Crypt Top Muscularis Crypt–villus

0.8

Slamf6

Slamf6

Klf2

0.6

axis

Klf2

Genes

0.4

Klrg1

Gzmb

0.2

Slamf6

Gzmb

Tcf7 Itgae

0

Klf2 Itgae

Itgae

0.150.3 0.6160.150.3 0.6160.150.3 0.6160.150.3 0.616

Gzmb

Itgae

Gzmb

Epithelial axis

0 1 0 1 0 1 0 1

Itgae

Gzma Gzmb Tcf7

Bottom Top

Bottom Top Bottom Top Bottom Top

- 0

0.5

1.0

- 1.5


1.0

1.0


---|---


0.125

Crypt–villus axis

Expression

0.8

0.8

0.100

###### i

0.6

0.6

0.075

Min. Max.

P14

0.4

0.4

0.050


Time (d.p.i.): 6 8 30 90

0.2

0.2

0.025


---|---

0

0

0

Itgae

Klrg1 Itgae Klf2

R1 R2 Crypt Top Muscularis

###### j

Mature TRM (cluster 29) Progenitor-like TRM (cluster 3)

Itgae Klrg1 Klf2 Tcf7 Slamf6 Il18r1 Ifng

Genes

Tcf7

Crypt–villus axis

1.0

1.0

1.0


---|---|


Klf2

0.125 0.100 0.075 0.050 0.025

Expression

Expression

0.8

0.8

0.8

Klf2 Tcf7 Il18r1 Slamf6

Slamf6

0.6

0.6

0.6

Ifng

0.4

0.4

0.4

Il18r1

0.2

0.2

0.2

Tcf7

Il18r1

Slamf6

0

0

0

0

0 1 0 1 0 1 0 1

0.150.30.616 0.150.30.616

IE LP

IE LP IE LP

IE LP

Epithelial axis

Epithelial axis

Epithelial axis

- Fig. 2 | Intestinal regionalization along key axes informs TRMcell diversity in the mouse intestine.a c, The spatial position and joint MDE embedding, coloured by their crypt–villus axis position (a), longitudinal axis position (b) and epithelial axis position (c). One of two biological replicates for each timepoint is shown.d, IMAPs of P14 CD8 T cells in samples from each timepoint (one of two replicates for each timepoint), with coloured gates dividing the top, crypt and muscularis (left) and the number of P14 CD8 T cells positioned in each gate across timepoints (two biological replicates for each timepoint) (right). Data are mean ± s.e.m.e, Combined time-course samples (n = 8, four timepoints with two biological replicates each) were pooled to create a swarm plot of Spearman rank correlation coefficients (ρ) between each axis and every gene expressed in at least 5% of P14 cells, with select correlated genes annotated. Genes are considered positively correlated (red) whenρ > 0.05, negatively correlated


(blue) whenρ < −0.05 and not correlated (grey) otherwise.f, The convolved gene expression of P14 CD8 T cells along the crypt–villus axis at every timepoint (n = 2 pooled biological replicates).g, IMAP representations of P14 CD8 T cells at 90 d.p.i. coloured by kernel density estimates weighted by expression counts of select genes (one of two biological replicates is shown).h, The expression of each gene in IMAP-gated regions of P14 CD8 T cells at 90 d.p.i. (n = 2 replicates, R1 and R2).i, The convolved gene expression of P14 CD8 T cells along the epithelial axis at every timepoint (n = 2 pooled biological replicates).j, IMAP representations of P14 CD8 T cells at 90 d.p.i. (one of two biological replicates is shown) coloured by kernel density estimates weighted by UCell signature enrichment of progenitor-like TRM cells (cluster 3 (ref. 12)) and differentiated TRM cells (terminal state, cluster 29)12 with signature scores in IMAP-gated regions (n = 2). IE, intraepithelial; LP, lamina propria; Max., maximum; Min., minimum.


a b Time (d.p.i.)

6 8 30 90

Immune

CD4

MAIT

Epithelial

P14 P14 P14 cDC1 Lymphatic

P14

Crypt

Fibroblast ILC

B cell DC

MAIT Monocyte

Endothelial Eosinophil

Myeloid NK

Epithelial absorptive Epithelial progenitor

Neuron T cell

Epithelial secretory Erythroid

c d


- e

B cell

CD4 T cell

CD8T cell

CD8T cell

Comp.  broblast

DC2

Early enterocyte

- Enterocyte 1


Enteroendocrine

Eosinophil

Fibroblast

+Ncam1 broblast

- +Pdgfra broblast
- +Pdgfrb broblast


Goblet

ILC

ISC

Lymphatic

MAIT

Macrophage

Megakaryocyte/platelet

Monocyte

Myoﬁbroblast

NK cell

Neuron

P14 crypt

P14 muscularis

P14 top

Paneth

Resting  broblast

T cell

T cell

Transit amplifying

Tuft

Vascular endothelial

cDC1

P14 top P14 crypt

P14 muscularis Min.

Max.

Co-localization

Tgfb1 Tgfb2 Tgfb3

- Il17b Ifng Tgfb3 Tgfb2 Cxcl10

Cxcl12 Il10

Il7 Il4 Il6

- Il18 Cx3cl1 Il17a Il21 Tgfb1


Xcl1

Il25 Il15

Crypt–villus axis

Pdgfra+

Ncam1

Complement

Myo.

Muscularis

Pdgfrb+

Resting

1 2

3

TA

ISC

Paneth

B DC2

Monocyte

EE Early Tuft

Goblet

Mac.

ILC

Bottom

Min.

Max.

Scaled expression

Min.

Max.

Min.

Max.

Scaled expression

Scaled expression

Top Crypt–villus axis

Bottom Top Bottom Top

Genes

0 1

Eosinophil

NK

Neuron Vascular

5 6 7 8 30 90 Time (d.p.i.)

Short-lived effectors

TRM precursors

Effector Early memory Late memory

Differentiated TRM Progenitor likeTRM

Cytokine gradient

Il15

Il18

Il7

Il2

- Tgfb1


Cxcl9/10

Villus

Crypt

Muscularis

LCMV-speci c

CD8 T cells

Gzmbhigh Gzmahigh Itgaehigh

Tcf1high Slamf6high

All cells

Bottom Top

Min.

Max.

- Tgfb1


- f


---|---|---|


|Time (d.p.i.)  6 8 30 90|Time (d.p.i.)  6 8 30 90|Time (d.p.i.)  6 8 30 90|
|---|---|---|


g

VWF Complement

Type II IFN

- 0


IL-2 MADCAM

PECAM1 VCAM

Tenascin THY1

Incoming signals

Collagen Laminin

CDH1 MHC-II

Notch ICAM

VTN CXCL

CD86 CD80

IL-1 ICOS

SELL IL-4

FN1 JAM

CCL TGF

Time (d.p.i.)

Top

6

P14

Crypt Muscularis

Top Crypt

8

P14

Muscularis

Top Crypt

30

P14

Muscularis

Top Crypt

90

P14

Muscularis


- Fig. 3 | Differential cytokine gradients and cellular communities across intestinal niches.a,b, A representation of the connectome between cell subtypes at an individual cell resolution in a villus at 8 d.p.i. (a) and an aggregated network format in which edges between nodes represent a normalized Squidpy interaction score lying above a 0.1 threshold (10% of the connections) (b). Node (x,y) positions were determined by running a Kamada–Kawai layout algorithm on the Squidpy interaction matrix of the two replicates at 8 d.p.i. Positions were visualized using igraph. For each timepoint, the interaction scores between nodes are averaged across the two biological replicates.c, Squidpy interaction scores between cell subtypes and P14-cell regional groupings—top, crypt and muscularis as depicted in Fig. 2d. The colour of the heat-map position reflects the strength of contact. Interaction scores are averaged across the eight samples, and values are row-normalized.d, The convolved gene expression


of cytokines along the crypt–villus axis ordered and displayed with scVelo pooled across all time-course samples for all cells (n = 8).e, Gene expression trends for TGFβ isoforms separated by timepoint (n = 2 biological replicates pooled) with representative TGFβ isoform expression depicted spatially at their positions on a villus from a SI (8 d.p.i.). A generalized additive model is used to fit a curve to the expression counts of each ligand along the crypt–villus axis, followed byz-score scaling for comparison across trends.f, A heat map showing the pathways contributing the most to incoming signalling of each P14-cell regional grouping. The relative strengths of each pathway were calculated using spatial CellChat onn = 2 samples from four timepoints.g, The spatiotemporal differentiation model for intestinal TRM cells. ISC, intestinal stem cell; cDC1, conventional type 1 dendritic cell; Comp, complement.

enterocytes (Fig. 3c). These data showed that the spatial polarization of TRM cell states includes a different set of cellular interactions, which could potentially contribute to inducing and maintaining this phenotypic diversity through local signals. To capture the potential for differential signalling along the villus, we focused on cytokine gradients along the crypt–villus axis captured in our Xenium dataset (Fig. 3d). Several key cytokines involved in TRM cell formation and maintenance showed pronounced expression gradients, including Il10 (ref. 23), Il7,Il21,Il15 (refs. 24,25) and TGFβ isoforms10 (Fig. 3d,e). An analysis of incoming signalling patterns in P14 CD8 T cells highlighted the MADCAM26, ICAM27, CCL, CXCL28 and TGFβ signalling pathways as differentially abundant along the crypt–villus axis, revealing their potential role as upstream regulators of the heterogeneity observed in TRM cell populations (Fig. 3f). These pathways encompass individual ligand– receptor interactions weighted by their prevalence (Supplementary Table 4). To obtain a more comprehensive view of cytokine gradients and validate our findings through an orthogonal approach, we profiled a mouse SI at 8 d.p.i. with LCMV infection using whole-genome spatial transcriptomics at 2 µm resolution (VisiumHD)29 (Extended Data Fig. 4a). Deconvolution of the crypt–villus axis revealed similar cytokine profiles to those found by Xenium, in addition to new ones not included in our Xenium gene panel (Extended Data Fig. 4b–d). To perform ligand–receptor analysis at single-cell resolution, we binned the 2-µm-resolution capture areas into H&E-segmented nuclei (Extended Data Fig. 4e). After cell typing and classification of CD8αβ T cells by their location in the villus, we observed differential incoming signals similar to those observed in Xenium mouse data, including the MADCAM, ICAM, CCL and CXCL families (Extended Data Fig. 4f and Supplementary Table 5).

These data indicate that signals in the SI architecture are poised to influence the influx of new CD8 T cells and steer their differentiation course. To test whether these signalling gradients exist before the infection onset, we performed Xenium profiling using a custom 480-gene panel (expanded from our original 350 genes; Supplementary Table 4) on two uninfected SIs. The data were highly correlated between the two biological duplicates (Extended Data Fig. 5a). Uninfected SIs showed a similar distribution of key cytokine expressions, including Tgfb1, Tgfb2,Tgfb3,Il18 andIl15 (Extended Data Fig. 5b), a similar connectome (Extended Data Fig. 5c) and a similar spatial polarization of CD8αβ T cells based on the expression of differentiated TRM cells (Gzma,Gzmb andItgae) and progenitor-like TRM cells (Tcf7 and Id3) (Extended Data Fig. 5d–f). Together, these data show that niche-dependent signals are poised to contribute both to differentiating incoming CD8 T cells as well as to maintaining the two polarized TRM cell states: a more differentiated TRM cells state at the top of the villus (high expression of Gzma, Gzmb andItgae) and a progenitor-like state around the crypt area (high expression ofTcf7 andSlamf6). These two distinct functional states are the opposite ends of a bimodal differentiation space and appear to be selected for and reinforced by their respective microenvironments over time (Fig. 3g).

###### TGFβ directs SI CD8 T cell positioning

TGFβ is an immunomodulatory cytokine that affects intestinal CD8 T cell homing and retention10,11and instructs TRMcell differentiation and maintenance4,30–32. Yet, how TGFβ signalling is spatially orchestrated in the SI is not well understood. Differential cellular communication analysis comparing P14 CD8 T cells at the crypt versus the top of the villus revealed a segregation of TGFβ isoform expression available to P14 CD8 T cells based on location (Extended Data Fig. 6a). As P14 CD8 T cells showed similar expression levels of Tgfbr1 and Tgfbr2 in the villus (Extended Data Fig. 6b), we posited that TGFβ signalling by CD8 T cells depends on their exposure to sources of TGFβ and/or cells that trans-present the active form of TGFβ on their surface through αβ integrins, such as αV (Itgav) coupled to β6 (Itgb6) or β8 (Itgb8)11.

For example, upper enterocytes (enterocyte type 1) did not express TGFβ isoforms but could, in theory, present TGFβ owing to expression ofItgav andItgb6 (Extended Data Fig. 6c). To mechanistically explore this idea, spatial transcriptomics profiling was conducted at 8 d.p.i. for the SI of mice that received wild-type or TGFβ receptor II (TGFβRII) knockout P14 CD8 T cells (Extended Data Fig. 6d). To incorporate more elements of the TGFβ signalling pathway, we designed an expanded 494-gene panel and used the MERSCOPE platform (Vizgen) (Extended Data Fig. 6e and Supplementary Table 7). This experiment generated a 470,000-cell dataset with an average of 186 transcripts per cell. TGFβRII knockout P14 CD8 T cells, labelled by the expression ofXistandCd8aand Cd8btranscripts, had an overall spatial distribution shifted towards the bottom of the villus and muscularis area and lowerItgaetranscripts than wild-type P14 CD8 T cells (Extended Data Fig. 6f,g). Their total numbers were not changed at this time after infection, as previously observed10 (Extended Data Fig. 6h). Differential gene expression between wild-type and TGFβRII knockout P14 CD8 T cells showed global downregulation of the core TRMcell signature5, as well as the TGFβ program (Extended Data Fig. 6i), includingItgae,Cxcr6,Cd160andP2rx7, and upregulation ofKlf2, Il18rap,S100a4andMki67, consistent with published regulation by TGFβ signalling33 (Extended Data Fig. 7a). Notably,Mki67was upregulated by TGFβRII knockout P14 CD8 T cells, andMki67+ TGFβRII knockout cells were preferentially located lower in the villus compared with wild-type cells, suggesting that the loss of adequate TGFβ programming caused an increased frequency of mislocalized proliferating cells (Extended Data Fig. 7b). To understand how P14 CD8 T cells engage in the TGFβ program on the basis of their proximity to other cell types, we used the top eight differentially expressed genes as a TGFβ signature and calculated a correlation with the nearest distance to different cell types (Extended Data Fig. 7c,d). Wild-type P14 CD8 T cells had the highest expression of the TGFβ program when closest to enterocytes and other cells at the top of the villus, and lowest when wild-type P14 CD8 T cells were in the proximity of cells located at the bottom of the villus (Extended Data Fig. 7d). TGFβRII knockout P14 CD8 T cells had a global loss of the transcription–distance correlation, consistent with the loss of TGFβ signals (Extended Data Fig. 7d). Gene-expression visualization of TGFβ isoforms and components of the trans-presentation machinery showed fibroblast populations to be producers, consistent with our Xenium dataset (Extended Data Figs. 6c and 7d). Next, we analysed differences in the physical distances between wild-type and TGFβRII knockout P14 CD8 T cells to each nearest cell type. These analyses showed an increased accumulation of TGFβRII knockout P14 CD8 T cells near fibroblasts and a concomitant distancing from enterocytes in the villus (Extended Data Fig. 7d,e and Supplementary Table 8). These changes were not explained by the compensatory expression of TGFβ molecules (Extended Data Fig. 7f). These data add to the current model of TRM cell differentiation by showing that CD103+TRMcell precursors, the population depleted by TGFβRII loss4, preferentially occupy the intravillous region and upper half of the villus, where they receive both TGFβ signalling and access to important cytokines for TRM cell differentiation and survival, such as IL-7 and IL-15 (refs. 32,34) (Extended Data Fig. 7g).

###### CXCR3-mediated SI CD8 T cell deployment

CXCR3 ligands, CXCL9 and CXCL10, are known T cell chemoattractants that contribute to T cell positioning and maturation in the SI28. However, it is unclear how these signals are distributed in the SI to program CD8 T cell fate. By looking at the expression of these two chemokines over the course of infection, we found that, althoughCxcl9 andCxcl10 signals were heavily enriched in the top half of the lamina propria during homeostasis, their expression was strongly induced after infection in C3-expressing fibroblasts (complement fibroblasts or adventitia fibroblasts), which are located at the bottom of the muscularis, creating a second potential attraction point for Cxcr3-expressing CD8 T cells (Fig. 4a,b). To test the role of these gradients in CD8 T cell location

and differentiation, we used a CRISPR–Cas9 approach to induceCxcr3 deletion in Cas9 P14 CD8 T cells. To optically identify single guide RNA (sgRNA)-containing cells using the Xenium assay, we introduced a pseudogene barcode in the 3′ untranslated region of the mCherry reporter used to sort the modified Cas9 P14 CD8 T cells. We also included Cas9 P14 CD8 T cells containing Cd19- and Thy1-targeting sgRNAs with different pseudogene barcodes as controls in the same experiment (Supplementary Table 9). After validation of their respective target genes by flow cytometry (Extended Data Fig. 8a), sgCxcr3, sgCd19 and sgThy1 P14 CD8 T cells were pooled at equal frequencies and transferred into mice, which were subsequently infected with LCMV (Fig. 4c). The pseudogene barcodes, unique for each sgRNA, used the same landing sequences as 3 genes included in the 350-gene panel that were the least expressed across all cells and undetectable in T cells (Extended Data Fig. 8b). At 8 d.p.i., the SI from two different mice that received the targeted T cells were profiled using the Xenium platform. Unique pseudogene barcodes were found almost exclusively in CD8 T cells (perturbed P14 CD8 T cells), and the number of barcodes detected per P14 cell was uniform across the crypt–villus axis (Fig. 4e and Extended Data Fig. 8b–d). sgRNA-transduced P14 CD8 T cells showed a significant decrease in their respective target genes (Fig. 4d). sgCxcr3-targeted P14 CD8 T cells had a marked upward shift in their villus positioning, with an enrichment in the top intraepithelial area of the villus, reduction in the lamina propria and almost no presence in the muscularis (Fig. 4e, Extended Data Fig. 8e and Supplementary Table 11). Analysis of gene expression by spatial gates showed thatCxcr3-deficient P14 CD8 T cells had increasedGzma andItgae expression and lowerKlf2 than control cells in certain regions (Fig. 4f). Thus, the loss of Cxcr3 induced a preferential accumulation of cells in the top intraepithelial area, and this positional shift further reinforced a more differentiated TRM cell phenotype (Fig. 4g). Loss of Cxcr3has been shown to deplete short-lived effector populations and to be required for the formation of CD103− TRM cells in the lamina propria without affecting intraepithelial TRMcell numbers28. Our data add to this model of differentiation by showing that short-lived effector cells are probably preferentially located in the lower half of the villus, crypt and stroma areas, attracted by CXCL9- and CXCL10-expressing immune and stromal cells in the lamina propria and muscularis early after infection. Together, these data highlight the causal connection between CD8 T cell location and phenotype and introduce an expandable approach for the spatial screening of perturbed T cells.

###### Spatial CD8 T cell programs in the human SI

To put the relevance of these findings into the context of human intestinal immunity, we profiled two terminal ilea from healthy donors using the Xenium platform with a custom immune-focused 422-gene panel (Extended Data Fig. 9a and Supplementary Table 10). Combined, we generated a dataset comprising 214,546 cells with an average of 89 median transcripts per cell and identified 38 different cell types (Fig. 5a and Extended Data Fig. 9b). Technical replicates (consecutive slides) were nearly identical, and the observed cell frequencies were similar between biological samples, except for B cells owing to differences in the abundance of Peyer’s patches (Fig. 5b and Extended Data Fig. 9c). IMAPs were computed by calculating the crypt–villus axis using spatial transcriptional neighbourhoods around each cell as a predictor for distance to the basal membrane and by calculating epithelial distance axes using the normalized distance to the nearest epithelial cells (Fig. 5c). First, to explore whether spatial distribution differences were observed between T cell populations, we focused on T cell types that emerged from unsupervised clustering (Extended Data Fig. 9d). CD8 T cells, proliferating T cells and γδ T cells were predominant in the top intraepithelial area, whereas effector T cells, includingGZMK+ CD8 T cells, were predominantly localized in the lamina propria and more evenly distributed along the crypt–villus axis (Extended Data Fig. 9e). These differences in location were reflected by their distinct

interactions with nearby cells (Extended Data Fig. 9f). Next, we focused our analysis on CD8αβ T cells outside the Peyer’s patches (Fig. 5c). Projecting the transcriptional signatures of the two spatially segregated P14 CD8 T cell populations we observed at 90 d.p.i. in mice, we identified similarly segregated subpopulations in human CD8αβ T cells (Fig. 5d). Furthermore, spatial differential expression analysis between human CD8αβ T cells in different morphological regions recapitulated the mouse findings, as many genes were spatially regulated, often similarly to their mouse homologues. These include GZMA and ITGAE, which localize near the epithelium at the top of the villus, andKLRG1andTCF7, which localize to the lamina propria and bottom of the villus as they do in mouse P14 CD8 T cells (Fig. 5e,f and Extended Data Fig. 9g). These data show that human intestinal CD8 T cells are similarly imprinted by their location in the tissue. Correlation analysis of gene expression in CD8 T cells with their relative distances to other cell types highlighted effector molecules ITGAE and GZMA to be most highly expressed by CD8αβ T cells when in proximity to enterocytes and the long-lived memory-associated molecule TCF7 to be most highly expressed by CD8αβ T cells when in proximity to CD4 T and B cells (Fig. 5g). Finally, differential cellular communication analysis between intestinal CD8 T cells, classified by the mouse spatial signatures (as in Fig. 5d), identified differential incoming signalling (Fig. 5h). Among these, ICAM (communication with vascular endothelial cells) was more prevalent in the progenitor-like-signature-enriched CD8αβ T cells, whereas C-type lectins and CC chemokine signalling (CCL, communication with other immune cells) were favoured for differentiated-signature-enriched CD8αβ T cells and TGFβ signalling was similar for both CD8αβ T cell subtypes (Fig. 5h and Supplementary Table 12). In summary, these data suggest that the heterogeneity in the phenotypes and gene expression observed in CD8 T cells in the SI is imprinted by their intratissue location, especially along the crypt–villus axis, which, through differential cellular interactions and exposure to chemokines and cytokine sources, such as TGFβ, maintains functionally different populations of CD8αβ T cells in both human and mouse.

###### Discussion

High-resolution spatial transcriptomics interrogation of mouse models of viral infection and human samples revealed that the intestinal cellular architecture shapes CD8 T cell diversity in the intestine. Our findings support a model in which the intestinal architecture creates localized instructive signals after infection through regionalization of cytokine secretion and distinct cellular interactions to produce fate-specifying areas that reinforce TRM cell precursor or short-lived effector CD8 T cell differentiation. Furthermore, spatial patterning throughout the crypt– villus and epithelial-distance axes reveals a distinct signalling potential that divides TRM cells into at least two distinct functional states. We observed similar signalling gradients and differentiation states in both mice and humans, epitomized by differentiated TRM cells at the intraepithelial top of the villi and progenitor-like TRM cells enriched in the lamina propria at the base of the villi.

Our data provide an understanding of how the TGFβ program is imparted on intestinal CD8 T cells to promote TRM cell programs in situ. Although many cells, both in mice and in humans, can express TGFβ isoforms (Extended Data Fig. 9h), the loss of TGFβRII leads to a preferential accumulation of CD8 T cells around fibroblasts in the lower villus area. This suggests that TGFβ signalling is required for TRM cells to find pro-survival and differentiation cues in the mid and upper areas of the villus whereIl7 andIl15 are more abundantly expressed. Of note, although enterocytes do not express detectable TGFβ in mice or humans, they do express ITGAV, which is required for the presentation of the active TGFβ signal (Extended Data Fig. 9h). In the skin, migratory dendritic cells use ITGAV to provide TGFβ stimulation to naive CD8 T cells to precondition a skin TRM cell fate, whereas keratinocytes maintain epidermal residence11,31. In the future, it will be important to

###### a

###### b

Time (d.p.i.)

Uninfected

6 d.p.i.

Cxcl10

Uninfected 6 8 30 90 B cell

Cxcl9 Cxcl10


0.2

0.1

CD4 T cell CD8 T cell CD8 T cell

0

Scaled expression

- –0.3


Complement  broblast DC2

Time (d.p.i.)

ILC MAIT

Cxcl9

0.20

Macrophage Monocyte NK cell cDC1

0.15

Uninfected

Fraction of cells in group

0.10

6 8 30 90

0.05

0

10 30 50 70 90

Cxcl9

Cxcl9

Cxcl9

Cxcl9

Cxcl9

Cxcl10

Cxcl10

Cxcl10

Cxcl10

Cxcl10

–0.05

Mean expression in group

Bottom Top


Crypt−villus axis

0 1

c

SI 8 d.p.i. (LCMV)


DAPI DAPI

sgCxcr3

sgCd19

- Cd8a

sgCd19

- Cd8b


sgCxcr3+ Itgae

sgCxcr3

- Cd8a

sgCd19

- Cd8b


###### d e

sgCd19 (1,547 cells)

sgCxcr3 (561 cells)

sgThy1 (1,030 cells)

Thy1

Cxcr3

***

*** 0.5 0.4 0.3 0.2 0.1

1.2 1.0 0.8 0.6 0.4 0.2

| |***|

100

| |46  26 30  32 17 16 8  24 18 10  31 15 14 9|
|---|---|
| |46  26 30  32 17 16 8  24 18 10  31 15 14 9|
| |46  26 30  32 17 16 8  24 18 10  31 15 14 9|
| |46  26 30  32 17 16 8  24 18 10  31 15 14 9|
| |46  26 30  32 17 16 8  24 18 10  31 15 14 9|
| |46  26 30  32 17 16 8  24 18 10  31 15 14 9
---|---
Proportion by gate

Crypt–villus axis

0.8

80

Expression

0.6

60

0.4

40

0.2

20

0 0

0

0

hy1 sg

Cxcr3

sgCd19 sg

sgCxcr3Thy1

d19 sgT

sgCxcr3gThy1

sgCd19

0.15 0.3 0.6 1 6

0.15 0.3 0.6 1 6 0.15 0.3 0.6 1 6

sgC

Epithelial axis

s

###### f

Itgae

Klf2

Gzma 1.6

###### *

0.7 ** 0.6 0.5 0.4 0.3 0.2 0.1

0.25

- 0.6

0.8

1.0

1.2

- 1.4 **


0.20

Expression

Expression

Expression

0.15

0.10

###### *

0.4

0.05

0.2

0

0

0

Muscularis

Muscularis

Muscularis

LP IE LP IE

LP IE LP IE

LP IE LP IE

Crypt Top

Crypt Top

Crypt Top

g

Cxcl9/10 sources

Cxcr3 KO Il15

WT

Top IE

Top LP

Crypt IE

Crypt LP

Muscularis

sgCd19

sgCxcr3

sgThy1

Cxcl9/10

TRM precursors

Short-lived effectors

Cxcl9/10

- Fig. 4 | CXCR3 promotes the early accumulation of short-lived effector cells in the lamina propria, lower villus area and muscularis.a, A dot plot ofCxcl9 andCxc10 expression in the indicated cells for time courses with and without infection.b, Gene expression trends forCxcl9 andCxcl10 (Cxcl9/10) separated by timepoint (n = 2 biological replicates pooled), with representative expression depicted spatially at their positions on the villus. Scale bar, 50 µm.c, sgRNAcontaining P14 CD8 T cells (yellow arrows, middle image) shown spatially in the intestinal villus at three levels of magnification as detailed by white rectangles from left to right. The left image is coloured by graph-based clustering. The red line (right image) indicates nuclear segmentation. Scale bar, 5 µm.d, The gene expression of each sgRNA-containing P14 CD8 T cell.n = 2 pooled biological


replicates with 1,548 sgCd19, 1,030 sgThy1 and 562 sgCxcr3 cells. Pairwise twosidedt-tests with Benjamini–Hochberg test correction. ***P < 0.001.e, An IMAP representation of each sgRNA-containing P14 CD8 T cell population with annotated percentages in each gate. f, The gene expression of each sgRNAcontaining P14 CD8 T cell split by spatial gate.n = 2 pooled biological replicates with cell numbers per gate shown in Supplementary Table 12. Pairwise twosidedt-test of the mean expression levels, with Benjamini–Hochberg correction.

*P < 0.05, **P < 0.01. Data are presented as mean ± s.e.m. (d,f).g, The proposed mechanism of CXCR3-dependent CD8 T cell villus distribution. KO, knockout; WT, wild type.

a


MDE 2

MDE 1

B cell CD4 GZMK+ CD8 effector CD8 T cell Conventional DC Effector T cell Enterocyte Enteroendocrine Fibroblast Goblet Lymphatic Macrophage Mast Monocyte Neuron Other DC Other myeloid PP CD4 T cell

PP CD8 T cell

PP GZMK+ CD8 T cell

Proliferating PP CD8 T cell PP T cell Paneth Plasma cell Proliferating myeloid Proliferating T cell GZMK++ITGAE T cell Other T cell (cluster 11) Other T cell (cluster 13) TA

Treg Tuft Vascular endothelial AQP1+ vascular endothelial CPE+ vascular endothelial cDC1

T cell

b

B cell CD4 T cell CD8 T cell

Conventional DC Endothelial Enterocyte

Enteroendocrine Fibroblast

T cell Goblet

Lymphatic Macrophage

Mast Monocyte

Myeloid

Neuron Other T cell

Other DC

Paneth PP immune

Tuft cDC1

Cell type frequency 0.1 0.2 0.3

c

Terminal ileum H&E Leiden Crypt–villus axis Epithelial axis All transcripts CD8 T cell


CD3E CD3D ITGAE

- CD8A


d

90 d.p.i. P14 top signature 90 d.p.i. P14 crypt signature

1.0


0.8

Crypt–villus axis

0.6


0.4

0.2

0

0 0.15 0.3 0.6 1 6

0 0.15 0.3 0.6 1 6

Epithelial axis

###### e

###### f

Crypt–villus axis Epithelial axis


KLRG1 TCF7

GZMA SLAMF6 ITGAE

SLAMF6

Genes

Genes

KLRG1

GZMA

TCF7 (top) 1 (LP) 1

ITGAE

0 (IE)

0 (bottom)

g h

Relative strength

Correlation of gene expression in CD8 T cells to the nearest cell type distance

0 1 Goblet

Enterocyte


B cell CD4 GZMK+ CD8 effector

T cell Conventional DC


0.4

Neuron Other DC

Myeloid Endothelial

CD8 T cell Differentiated CD8 TRM

0.2

Correlation

Fibroblast Mast

0

Progenitor-like CD8 TRM

Tuft Paneth

cDC1 Conventional DC

Enteroendocrine Macrophage Lymphatic cDC1

- –0.4


Effector T cell Other DC Proliferating T cell GZMK+ITGAE+ T cell

Other T cell Monocyte CD4 T cell

B cell Peyer patches

ITGAEGZMANT5ESLAMF6KLF2EOMESTCF7GZMK

CEACAM CLECBAFFXCR ICAMIL-2 ITGB2CCL

PECAM1 TGF

Incoming signals

- Fig. 5 | CD8 T cell phenotypic diversity in the human ileum is spatially imprinted.a,b, Spatial transcriptomics of two human terminal ileum sections using 10x Xenium: joint MDE embedding coloured by cell type (a) and mean relative frequencies of each cell type pooled across all sections (b). Data show mean ± s.e.m. Two adjacent sections per donor.c, An overview of the human Xenium data. From left to right: terminal ileum with cell masks coloured by cell type; villus magnification showing H&E staining and Xenium DAPI staining with cell boundaries overlaid and coloured by Leiden cluster, crypt–villus axis and epithelial distance; further zoom-in showing Xenium DAPI with cell masks and detected transcripts and select transcripts overlaid over DAPI staining (1 representative ofn = 1,423 CD8αβ T cells). Scale bar, 300 µm.d, An IMAP representation of CD8αβ T cells coloured by kernel density estimates weighted by mouse P14 cell signatures at the top of the villus (left) or or crypt (right). The human IMAP gates define the top villus (blue) and crypt (red), split into intraepithelial (left) and lamina propria (right). CD8αβ T cells were pooled


across all replicates (n = 1,423); Peyer’s patches (PP) excluded.e,f, The convolved gene expression of CD8αβ T cells along the crypt–villus axis (e) and epithelial axis (f). All human samples were pooled (n = 2 donors, two adjacent sections each), excluding Peyer’s patches.g, The expression of select genes in CD8 T cells are Spearman rank correlated with distances to other cell types. Red indicates that expression increases when CD8 T cells are near, whereas blue indicates that expression decreases. Correlations calculated per sample (n = 4); mean coefficient shown.h, A heat map showing the top pathways contributing to incoming signalling of different immune cell groupings. Relative strengths calculated using spatial CellChat on all human samples. The heat map was column-normalized across all cell subtypes; only specific immune subtypes are shown. CD8αβ T cells grouped as effector or stem-like on the basis of enrichment of mouse-derived UCell signatures. Enrichmentz-scored before classifying CD8αβ T cells. CLEC, C-type lectins; Treg, T regulatory cell.

determine to what extent TGFβ presentation by specific cell types is needed to maintain intraepithelial CD8 T cell populations.

Newly infiltrated effector CD8 T cells responding to an infection in the SI display high interstitial motility, which becomes more restricted as cells differentiate into TRM cells35. Thus, signals received during the high-motility phase, such as short- and long-range sensing of chemokines and cytokines, might ultimately condition the destination of TRMcells in the tissue. Increased chemotactic signals, such asCxcl9andCxcl10, at the base of the muscularis might be responsible for the accumulation of short-lived effector cells observed in the few days after infection. The presence of inducible chemotactic areas rather than stable gradients in the villus creates a network that can steer incoming new CD8 T cell infiltrates while maintaining the polarization of tissue-resident populations.

Our in vivo approaches, the optically encoded perturbations and computational analyses to systematically study the spatial positioning of TRMcells in the SI could also be applied to other tissues with functional repetitive structures, such as the nephron in the kidney, glandular structures or hepatic lobule and similarly provide a framework for the study of other immune cell populations in tissues. Insights from this approach inform avenues to selectively target tissue-specific immune populations, functional subsets and the interactions driving immune cell function in a given tissue30,36,37.

###### Online content

Any methods, additional references, Nature Portfolio reporting summaries, source data, extended data, supplementary information, acknowledgements, peer review information; details of author contributions and competing interests; and statements of data and code availability are available at https://doi.org/10.1038/s41586-024-08466-x.

- 1. Milner, J. J. et al. Heterogenous populations of tissue-resident CD8+ T cells are generated in response to infection and malignancy. Immunity 52, 808–824 (2020).
- 2. Masopust, D. & Soerens, A. G. Tissue-resident T cells and other resident leukocytes. Annu. Rev. Immunol. https://doi.org/10.1146/annurev-immunol-042617-053214 (2019).
- 3. Reina-Campos, M. et al. Metabolic programs of T cell tissue residency empower tumour immunity. Nature 621, 179–187 (2023).
- 4. Crowl, J. et al. Tissue-resident memory CD8+ T cells possess unique transcriptional, epigenetic and functional adaptations to different tissue environments. Nat. Immunol. 23, 1121–1131 (2022).
- 5. Milner, J. J. et al. Runx3 programs CD8+ T cell residency in non-lymphoid tissues and tumours. Nature 552, 253–257 (2017).
- 6. Heeg, M. & Goldrath, A. W. Insights into phenotypic and functional CD8 TRM heterogeneity. Immunol. Rev. 316, 8–22 (2023).
- 7. Qiu, Z. et al. Retinoic acid signaling during priming licenses intestinal CD103+ CD8 TRM cell differentiation. J. Exp. Med. 220, e20210923 (2023).
- 8. Masopust, D., Vezys, V., Wherry, E. J., Barber, D. L. & Ahmed, R. Cutting edge: gut microenvironment promotes differentiation of a unique memory CD8 T cell population. J. Immunol. 176, 2079–2083 (2006).
- 9. MacKay, L. K. et al. The developmental pathway for CD103+ CD8+ tissue-resident memory T cells of skin. Nat. Immunol. 14, 1294–1301 (2013).
- 10. Zhang, N. & Bevan, M. J. Transforming growth factor-β signaling controls the formation and maintenance of gut-resident memory T cells by regulating migration and retention. Immunity 39, 687–696 (2013).
- 11. Mohammed, J. et al. Stromal cells control the epithelial residence of DCs and memory T cells by regulated activation of TGF-β. Nat. Immunol. 17, 414–421 (2016).
- 12. Kurd, N. S. et al. Early precursors and molecular determinants of tissue-resident memory CD8+ T lymphocytes revealed by single-cell RNA sequencing. Sci. Immunol. 5, eaaz6894

(2020).

- 13. Lin, Y. H. et al. Small intestine and colon tissue-resident memory CD8+ T cells exhibit molecular heterogeneity and differential dependence on Eomes. Immunity 56, 207–223


(2023).

- 14. Hickey, J. W. et al. Organization of the human intestine at single-cell resolution. Nature 619, 572–584 (2023).
- 15. Zwick, R. K. et al. Epithelial zonation along the mouse and human small intestine defines five discrete metabolic domains. Nat. Cell Biol. 26, 250–262 (2024).
- 16. Harnik, Y. et al. A spatial expression atlas of the adult human proximal small intestine. Nature 632, 1101–1109 (2024).
- 17. Janesick, A. et al. High resolution mapping of the tumor microenvironment using integrated single-cell, spatial and in situ analysis. Nat. Commun. 14, 8353 (2023).
- 18. Gyllborg, D. et al. Hybridization-based in situ sequencing (HybISS): spatial transcriptomic detection in human and mouse brain tissue. Nucleic Acids Res. https://doi.org/10.1093/ nar/gkaa792 (2020).
- 19. Covert, I. et al. Predictive and robust gene selection for spatial transcriptomics. Nat. Commun. 14, 2091 (2023).
- 20. Heng, T. S. P. et al. The Immunological Genome Project: networks of gene expression in immune cells. Nat. Immunol. 9, 1091–1094 (2008).
- 21. Browaeys, R., Saelens, W. & Saeys, Y. NicheNet: modeling intercellular communication by linking ligands to target genes. Nat. Methods 17, 159–162 (2019).
- 22. Moor, A. E. et al. Spatial reconstruction of single enterocytes uncovers broad zonation along the intestinal villus axis. Cell 175, 1156–1167 (2018).
- 23. Thompson, E. A. et al. Monocytes acquire the ability to prime tissue-resident T cells via IL-10-mediated TGF-β release. Cell Rep. 28, 1127–1135 (2019).
- 24. Jarjour, N. N. et al. Responsiveness to interleukin-15 therapy is shared between tissueresident and circulating memory CD8+ T cell subsets. Proc. Natl Acad. Sci. USA 119, e2209021119 (2022).
- 25. Schenkel, J. M. et al. IL-15-independent maintenance of tissue-resident and boosted effector memory CD8 T cells. J. Immunol. 196, 3920–3926 (2016).
- 26. Vimonpatranon, S. et al. MAdCAM-1 costimulation in the presence of retinoic acid and TGF-β promotes HIV infection and differentiation of CD4+ T cells into CCR5+ TRM-like cells. PLoS Pathog. 19, e1011209 (2023).
- 27. McNamara, H. A. et al. Up-regulation of LFA-1 allows liver-resident memory T cells to patrol and remain in the hepatic sinusoids. Sci. Immunol. https://doi.org/10.1126/ sciimmunol.aaj1996 (2017).
- 28. Bergsbaken, T. & Bevan, M. J. Proinflammatory microenvironments within the intestine regulate the differentiation of tissue-resident CD8 T cells responding to infection. Nat. Immunol. 16, 406–414 (2015).
- 29. Oliveira, M. F. et al. Characterization of immune cell populations in the tumor microenvironment of colorectal cancer using high definition spatial profiling. Preprint at bioRxiv https://doi.org/10.1101/2024.06.04.597233 (2024).
- 30. Christo, S. N. et al. Discrete tissue microenvironments instruct diversity in resident memory T cell function and plasticity. Nat. Immunol. 22, 1140–1151 (2021).
- 31. Mani, V. et al. Migratory DCs activate TGF-β to precondition naïve CD8+ T cells for tissue-resident memory fate. Science 366, eaav5728 (2019).
- 32. Mackay, L. K. et al. T-box transcription factors combine with the cytokines TGF-β and IL-15 to control tissue-resident memory T cell fate. Immunity 43, 1101–1111 (2015).
- 33. Borges da Silva, H. et al. Sensing of ATP via the purinergic receptor P2RX7 promotes CD8+ Trm cell generation by enhancing their sensitivity to the cytokine TGF-β. Immunity https:// doi.org/10.1016/j.immuni.2020.06.010 (2020).
- 34. Jarjour, N. N. et al. Collaboration between IL-7 and IL-15 enables adaptation of tissueresident and circulating memory CD8+ T cells. Preprint at bioRxiv https://doi.org/10.1101/ 2024.05.31.596695 (2024).
- 35. Thompson, E. A. et al. Interstitial migration of CD8αβ T cells in the small intestine is dynamic and is dictated by environmental cues. Cell Rep. 26, 2859–2867 (2019).
- 36. Evrard, M. et al. Single-cell protein expression profiling resolves circulating and resident memory T cell diversity across tissues and infection contexts. Immunity 56, 1664–1680

(2023).

- 37. Park, S. L. et al. Divergent molecular networks program functionally distinct CD8+ skin-resident memory T cells. Science 382, 1073–1079 (2023).


Publisher’s noteSpringer Nature remains neutral with regard to jurisdictional claims in published maps and institutional affiliations.

Open AccessThis article is licensed under a Creative Commons Attribution 4.0 International License, which permits use, sharing, adaptation, distribution and reproduction in any medium or format, as long as you give appropriate

credit to the original author(s) and the source, provide a link to the Creative Commons licence, and indicate if changes were made. The images or other third party material in this article are included in the article’s Creative Commons licence, unless indicated otherwise in a credit line to the material. If material is not included in the article’s Creative Commons licence and your intended use is not permitted by statutory regulation or exceeds the permitted use, you will need to obtain permission directly from the copyright holder. To view a copy of this licence, visit http://creativecommons.org/licenses/by/4.0/.

© The Author(s) 2025

###### Methods

###### Mice

Mice were maintained in specific-pathogen-free conditions at a temperature between 18 °C and 23 °C with 40–60% humidity and a 12 h–12 h light–dark cycle in accordance with the Institutional Animal Care and Use Committee of the University of California, San Diego (UCSD). All mice were of C57BL/6J background and bred at the UCSD or purchased from The Jackson Laboratory.R26creERT2 (stock no. 008463, The Jackson Laboratory),Tgfbr2fl/fl (stock no. 012603, The Jackson Laboratory), P14 Cas9–eGFP (stock no. 026179, The Jackson Laboratory), P14 and CD45.1 congenic mice were bred in-house. Male recipient mice were used for adoptive transfer experiments, and females were used as P14 CD8 T cell donors. In the spatial pooled CRISPR knockout experiment, a male was used as a donor. To delete floxed alleles using Cre-ERT2, 1 mg of tamoxifen (Cayman Chemical) emulsified in 100 µl of sunflower seed oil (Sigma-Aldrich) was administered by intraperitoneal injection for five consecutive days to P14R26creERT2Tgfbr2WT(WT) and P14R26creERT2Tgfbr2fl/fl (TGFβRII knockout) mice before P14 CD8 T cell isolation. All mice were between 1.5 and 6 months old at the time of infection and randomly assigned to experimental groups. No statistical methods were used to predetermine sample sizes, but our sample sizes are similar to those reported in previous publications from our laboratory and others. No blinding was performed during mouse experiments. Investigators were not blinded to group allocation during data collection and/or analysis. Mice were fed ad libitum for the specified amount of time. All animal studies were approved by the Institutional Animal Care and Use Committee at the UCSD and performed in accordance with UCSD guidelines.

###### Adoptive cell transfer of naive P14 CD8 T cells and LCMV infection in mice

A total of 5 × 104female naive P14 CD8 T cells isolated by negative enrichment using magnetic activated cell sorting (MACS) and resuspended in PBS were transferred intravenously into congenically distinct male recipient mice. Recipient mice were subsequently infected intraperitoneally with 2 × 105 plaque-forming units of the Armstrong strain of LCMV.

###### Preparation of single-cell suspensions for flow cytometry

The isolation of CD8 T cells was performed as described previously38. SI intraepithelial lymphocytes and lamina propria lymphocytes were prepared by removing Peyer’s patches and the luminal contents from the entire SI. The SI was then cut longitudinally into 1 cm pieces and incubated at 37 °C for 30 min in HBSS with 2.1 mg ml−1 sodium bicarbonate, 2.4 mg ml−1 HEPES, 8% bovine growth serum and 0.154 mg ml−1 dithioerythritol (EMD Millipore). The samples were passed through a 70-µm cell strainer, and the supernatant constituted the intraepithelial lymphocyte compartment of the SI. The remaining tissue fragments of the SI were further incubated in RPMI with 1.2 mg ml−1 HEPES, 292 µg ml−1 l-glutamine, 1 mM MgCl2, 1 mM CaCl2, 5% fetal bovine serum (FBS) and 100 U ml−1 collagenase (Worthington) at 37 °C for 30 min. After enzymatic incubation, samples were filtered through a 70-µm nylon cell strainer (Falcon). Tissue preparations were separated on a 44%/67% Percoll density gradient.

The following antibodies were used for flow cytometry: CD3 (PE clone 145-2C11, eBioscience 12-0031-83, 1:200 dilution), TCR αβ (APC clone H57-597, eBioscience 17-5961-83, 1:200 dilution), NK1.1 (FITC clone PK136, eBioscience 11-5941-81, 1:400 dilution), CD19 (PerCP-Cy5.5 clone eBio1D3, eBioscience 45-0193-82, 1:200 dilution), CD8b (BV421 clone H35-17.2, eBioscience 48-0083-82, 1:400 dilution), CD45.1 (BV510 clone A20, BioLegend 110741, 1:200 dilution), TCR γδ (BV711 clone GL3, BioLegend 118149, 1:200 dilution), CD4 (BV786 clone GK1.5, BioLegend 100453, 1:400 dilution), CD8a (PE-Cy7 clone 53-6.7, eBioscience 25-0081-82, 1:400 dilution), fixable viability dye (APC-Cy7 eBioscience 65-0865-14, 1:1,000), CD11b (PE clone M1/70, eBioscience

12-0112-82, 1:200 dilution), CD11c (APC clone N418, BioLegend 117310, 1:200 dilution), Ly6C (FITC clone AL-21, BD 553104, 1:200 dilution), Ly6G (PerCP-Cy5.5 clone 1A8, BioLegend 127615, 1:200 dilution), XCR1 (BV421 clone ZET, BioLegend 148216, 1:200 dilution), CD45 (BV510 clone 30-F11, BD 561487, 1:200 dilution), F4/80 (BV711 clone BM8, BioLegend 123147, 1:200 dilution), MHC II (BV786 clone M5/114.15.2, BioLegend 107645, 1:200 dilution) and B220 (PE-Cy7 clone RA3-6 B2, BioLegend 103222, 1:200 dilution).

###### Sample preparation for histology of the mouse SI

For fresh frozen samples, mouse SIs were collected, retaining the proximal–distal orientation. After discarding the first 3 cm proximal section, approximately 10 cm of mouse proximal SI (containing duodenum and proximal jejunum) was rinsed in ice-cold PBS and the lumen contents were flushed with 20 ml of ice-cold PBS using a gavage syringe. The SI was then loaded onto a 3.25-mm-diameter knitting needle premoistened with cold PBS and placed directly on thick blotting paper. The Mouse Intestinal Slicing Tool39 was used as a guide for the scalpel to cut the intestine longitudinally along the knitting needle. The Mouse Intestinal Slicing Tool and needle were removed, and the SI was spread open and rolled using a wood autoclaved round toothpick, embedded in OCT in plastic moulds, frozen in dry ice(Tissue-Tek Cryomold) and kept at −80 °C until cryosectioning. For fixed frozen samples, the opened cleaned SIs were fastened to blotting paper by minutien pins in each corner and fixed in 4% paraformaldehyde solution in PBS at 4 °C for 16 h, followed by incubation in 70% ethanol at 4 °C for a minimum of 3 h. The SI samples were then rolled using a wood autoclaved round toothpick, snap-frozen in OCT in plastic moulds for cryosection (Tissue-Tek Cryomold) and kept at −80 °C until processing. For formalin-fixed paraffin-embedded (FFPE) samples, fixed SIs were rolled, mounted on 2% agar round moulds and placed on histology cassettes for paraffin embedding.

###### Histology and immunofluorescence staining of fresh frozen mouse tissues

After OCT block equilibration at −20 °C, 10-mm slices were obtained using a cryostat, mounted on glass slides, dried for 20 min at −20 °C and fixed in ice-cold acetone at −20 °C for 20 min. After fixation, the slides were dried briefly at room temperature and stored at −80 °C until stained or used immediately. For staining, the slides were equilibrated at room temperature, washed in 4 °C PBS twice for 5 min, blocked in serum-free blocking reagent overnight (Dako) at 4 °C, followed by staining with CD45.1–AF594 (BioLegend, clone A20, 110756, 1:50 dilution) and E-cadherin-APC (BioLegend, clone DECMA-1, 147312, 1:200 dilution) and CD8a–FITC (BioLegend, clone 53-6.7, 35-0081-U500, 1:50 dilution) diluted in antibody diluent solution (Dako, S080983-2) overnight at 4 °C, stained with DAPI and mounted with coverslips using Vectashield Vibrance Antifade mounting medium (VectorLabs, H-1700). Images were acquired on an Olympus VS200 Slide Scanner (UCSD Microscopy Core) or on a Zeiss LSM700 confocal microscope. P14 CD8 T cell distances for IMAP representation over time were quantified using a groovy script on QuPath (https://github.com/Goldrathlab/ Spatial-TRM-paper).

###### Single-nucleus RNA-seq of mouse SI

Female CD45.1+CD8+ P14 T cells were adoptively transferred into male CD45.2 recipients (1 × 105cells per mouse) 30 min before infection with the Armstrong strain of LCMV. At 28 d.p.i., the mice were euthanized and the SI was dissected, flayed and washed in cold PBS; Peyer’s patches were excised from the SI. The SI was divided into three equal sections designated as the proximal, middle and distal SI. Tissue sections were cut into pieces of approximately 3 mm and flash-frozen in liquid nitrogen for 2 min. Nucleus isolation was performed with 10x Genomics Chromium Nuclei Isolation Kit per the manufacturer’s instructions. In brief, 30–50 mg of flash-frozen tissue per sample was dissociated

with a pestle, incubated for 10 min on ice and washed. Dissociated tissue was passed through a nucleus isolation column, and flowthrough nuclei were washed in debris removal buffer and wash and resuspension buffer. Nuclei were quantified with a Nexcelom Bioscience Cellometer. For maximum targeted recovery, 40,000 nuclei per sample were loaded for Gel Bead-In Emulsion generation. Samples were processed by the Chromium Next GEM Single Cell 3′ HT Dual Index v3.1 protocol and sequenced to a depth of 550 million read pairs per sample (around 23,000 read pairs per nucleus) on a NovaSeq 6000 system (Illumina).

###### Spatial transcriptomics analysis using whole-genome spatial transcriptomics (VisiumHD)

A 7-µm-thick section from an 8 d.p.i. FFPE sample was placed in a histology slide, dried at 42 °C for 3 h, dehydrated overnight, baked at 60 °C for 30 min and deparaffinized following the VisiumHD stand-

- ard protocol (CG000685). The mouse reagents (VisiumHD, Mouse Transcriptome, 6.5 mm, four reactions, PN-1000676) were used to obtain high-quality H&E images, perform hybridization, RNA removal and probe amplification, carry out analyte transfer to the VisiumHD slide using the Cytassist with the 2.0 software, and generate libraries, which were sequenced following the recommended configuration in a NovaSeq 6000 Illumina instrument. Binary base call files were demultiplexed into FASTQ files using spaceranger mkfastq followed by spaceranger count to generate the spatial representation of gene counts by matrix at 2-mm-resolution and 8-mm-resolution binning. A Cellpose40cell-segmentation model was fine-tuned to segment nuclei in the high-resolution VisiumHD H&E image. A cell-by-gene matrix was created by summing transcript counts in all 2 mm bins overlapping each cell in the segmentation mask. gimVI was used to jointly embed cells from an 8 d.p.i. Xenium dataset with those from 8 d.p.i. VisiumHD41. The crypt–villus axis and cell types for VisiumHD were imputed by using the three closest Xenium neighbours in the joint latent space. The crypt–villus axis values were calculated as the mean of the neighbours’ values, whereas the cell type was determined by the most frequently occurring type among the neighbours. Further details of the downstream analysis of the VisiumHD dataset are provided at GitHub (https://github.com/Goldrathlab/Spatial-TRM-paper).


###### Spatial transcriptomics analysis using multiple error-robust fluorescence in situ hybridization

Fresh frozen tissue was sectioned according to standard histology procedures to a thickness of 10 µm. The sections were adhered to the MERSCOPE slides (Vizgen, 20400001) coated with fluorescent beads by storing them in the cryostat at −20 °C for at least 5 min. The samples were fixed in 5 ml of fixation buffer containing 4% paraformaldehyde in 1× PBS that was preheated to 47 °C and incubated for 30 min at 47 °C, according to the MERSCOPE Quick Guide Modified Fixation for Fresh Frozen Samples. The samples were then washed three times with 5 ml PBS, 5 min each time. The samples were permeabilized in 5 ml 70% ethanol at 4 °C in parafilm-sealed dishes overnight and stored in these conditions for up to a month. Samples were then prepared according to Vizgen’s protocols, starting from the cell-boundary protein-staining step. The samples were hybridized with a custom 500-gene panel that included 5 sequential genes, as well as several blank barcodes that do not encode a gene and used for measuring the background signal. To clear the samples of lipids and proteins that interfere with imaging, 5 ml of Clearing Premix (Vizgen, 20300003) was mixed with 100 µl of proteinase K for each sample, and the samples were placed at 47 °C in a humidified incubator overnight (or for a maximum of 24 h) and then moved to 37 °C. The samples were stored in the clearing solution provided with the MERSCOPE kit in the 37 °C incubator before imaging for up to a week. The samples were imaged on the MERSCOPE according to the MERSCOPE Instrument User Guide. Seven 1.5-µm-thickz planes were imaged for each field of view at 60× magnification. Images were decoded to RNA spots withxyz and gene ID using the Merlin software

of Vizgen. Cell segmentation was performed using the Cellboundary algorithm, relying on the Cellboundary 2 stain and DAPI nuclear seeds.

###### Spatial transcriptomics analysis using 10x Xenium

FFPE tissues were sectioned to a thickness of 5 µm onto a Xenium slide, followed by deparaffinization and permeabilization following the 10x user guides CG000578 and CG000580. Probe hybridization, ligation and amplification were done following the 10x user guide CG000582. In brief, probe hybridization occurred at 50 °C overnight with a probe concentration of 10 nM using a custom gene panel designed to detect 350 different mRNAs. After stringent washing to remove unhybridized probes, probes were ligated at 37 °C for 2 h. During this step, a rolling circle amplification primer was also annealed. The circularized probes were then enzymatically amplified (2 h at 37 °C), generating multiple copies of the gene-specific barcode for each RNA binding event. After washing, background fluorescence was quenched chemically. The sections were placed into an imaging cassette to be loaded onto the Xenium Analyzer instrument following the 10x user guide CG000584.

###### Spatial data processing

For 10x Xenium spatial transcriptomics data, nuclei were segmented using a fine-tuned Cellpose40 model on maximum-projected DAPIstaining images. Baysor42 was used to predict cell-boundary segmentations using transcript identity and positions, and the prior Cellpose nuclei segmentation or Cellboundary 2 segmentation for 10x Xenium or MERSCOPE, respectively. The parameter prior-segmentation-confidence was set to 0.95 for 10x Xenium and to 0.9 for MERSCOPE, and min-molecules-per-cell was set to the median nucleus transcript count (https://github.com/Goldrathlab/Spatial-TRM-paper#preprocessing). Baysor segmentations containing no nuclei were filtered out, and segmentations containing multiple nuclei were split by assigning transcripts to the nearest nucleus centroid in the segmentation boundary. Cell boundaries are visualized as polygons using the alphashape Python package. All cells withn < 8 nuclear transcripts,n < 20 total transcripts orn > 800 total transcripts were filtered out before downstream processing. To integrate spatial replicates into a joint embedding, scVI43 was used with n_layers of 2 and n_latent of 30. The joint embedding was projected into two-dimensional space using scVI.model.utils.mde. Leiden clustering was performed on the scVI learned embeddings using scanpy.tl.leiden with a resolution of 1, and every Leiden cluster was further subclustered at a resolution of 1.2. Celltypist44 and GeneFormer45 were used for a first-pass cell type assignment, with further manual refinement based on the expression of cell type marker genes to define cell types in a class > type > subtype hierarchy. The Anndata46 format was used for all further processing. To align histology images with Xenium spatial coordinates, we used an OpenCV Oriented FAST and Rotated BRIEF47 object to detect key points in the DAPI channel of both histology and Xenium images. These key points were then matched using an OpenCV DescriptorMatcher, enabling the computation of a homography matrix based on the top matches using cv2.findHomography. Subsequently, histology images across all channels underwent warping using this homography matrix with cv2.warpPerspective. To align H&E images with Xenium spatial coordinates, we trained a pix2pix generative adversarial network48,49 to predict DAPI images from H&E as an intermediate state before finding key points and matching, as previously mentioned. To visualize mouse transcriptional signatures onto human datasets, all (n = 8) mice time course samples were used to find the top 15 differentially expressed genes (Scanpy rank_genes_groups and method = ‘wilcoxon’) between P14 cells gated to the crypt and P14 cells gated to the top of villi. Human homologues of these 15 genes are defined as UCell50 signatures and mapped to human CD8αβ T cells. Human CD8αβ T cells are positioned on IMAPs and coloured by their enrichment of the (left) top mouse signature and (right) crypt mouse signature. All codes to analyse the spatial datasets are available at https:// github.com/Goldrathlab/Spatial-TRM-paper.

###### Histological staining of mouse intestinal tissue after Xenium analysis

After the Xenium run, slides were kept hydrated in PBS-T (0.05% Tween-20 in PBS) at 4 °C. For post-Xenium immunofluorescence staining, PBS-T was removed and samples were blocked using universal blocking reagent CAS-Block and stained with anti-CD8a antibody (Abcam, EPR21769) 1:50 dilution) overnight at 4 °C, followed by three washes with PBS. Anti-rabbit AF594 secondary antibody (Invitrogen, A-11012, 1:200 dilution) in Dako antibody diluent was then added for 1 h at room temperature in the dark, followed by three washes with PBS. The slides were then stained using WGA–FITC followed by DAPI staining and then mounted with a coverslip using Vectashield mounting medium. The slides were dried for 1 h at room temperature in the dark before imaging with an Olympus VS200 Slide Scanner at 20×. The slides were then soaked in PBS at 4 °C overnight to dismount the coverslip and subsequently washed three times in PBS and twice in ddH2O before proceeding with H&E staining. The coverslip was mounted using xylene-based mounting medium (Cytoseal XYL Epredia), and the slides were dried for 1 h and imaged used VS200 Slide Scanner at 20×.

###### Human samples

Deidentified human FFPE samples from healthy participants were acquired from the San Diego Digestive Diseases Research Center. Slices of 5 mm were obtained using a microtome, deparaffinized and H&E stained according to common histology practices or processed according to the 10x Xenium protocol.

###### Human participants and ethical statement

The Human Research Protection Programs at the UCSD reviewed and approved the protocol, including a waiver of consent. Submucosal ileal biopsies were obtained from patients who underwent colonoscopies to rule out inflammatory bowel diseases. Ileal biopsies were evaluated by a pathologist and found to be normal without histological inflammation. Samples were deidentified and processed for the study.

###### Gene panel design for probe-based spatial transcriptomics profiling of mouse SI

The gene panel design made use of Predictive and Robust Gene Selection for Spatial Transcriptomics (PERSIST)19, a deep learning model that uses single-cell RNA sequencing (scRNA-seq) data to learn a binary mask for the identification of a subset of genes that best predict cell type from gene expression (supervised) or for the reconstruction of whole-transcriptome gene expression (unsupervised). For the Xenium mouse 350-gene panel, 79 SI canonical cell type marker genes were compiled from existing literature andXist, a marker for transferred female P14 CD8 T cells. An additional 158 genes from a Nichenet database21of ligand– receptor pairs were included. Next, supervised PERSIST was run on an immune-enriched gut scRNA-seq dataset51with the previously compiled set of genes as prior information, adding an additional 70 genes. Finally, supervised PERSIST was run on a SI scRNA-seq dataset to capture 59 cell type marker genes for 350 total targets. To create the Xenium human 422-gene panel, we created a base set of canonical immune marker genes, ligand–receptor pairs, spatially differentially expressed genes in mouse P14 CD8 T cells, and the 10x Genomics base human colon panel totalling 343 genes. Using this set as prior information for PERSIST, and a reference human immune cell scRNA-seq dataset52, unsupervised PERSIST filled in the remaining 79 genes. To create the 494-gene panel for MERSCOPE, we compiled 18 published bulk RNA-seq datasets profiling different immune populations in different disease settings5,53–66, including the ImmGen RNAseq database (immgen.org), and manually curated metadata attributes for each sample for the following categories: cell. main, cell.type, cell.subtype, cell.state, model and tissue. The annotated integrated dataset compilation was used as input for feature selection with XGBoost67. Top genes in each attribute were incorporated as the

panel backbone. Furthermore, gene markers of intestinal cell markers from PanglaoDB and ref. 68, ImmGen CITE-seq protein markers and 159 genes from the ligand–receptor database NicheNet21 were added. A total of 494 final genes passed the quality-check filtering of Vizgen for transcript length and expression levels. The Xenium mouse 480-gene panel was designed using the 350-gene panel but removing genes that were minimally informative based on the time course data and adding genes that were relevant based on manual curation and a prioritization score that evaluates their ability to differentiate clusters in a scRNA-seq dataset containing most cell types of the mouse SI69.

###### Defining structural axes in spatial transcriptomics datasets of the SI

To calculate the longitudinal axis, a multiline segment was initially labelled across the base of the basal membrane, using labelme70, starting from the outermost section of the roll. For each cell, the nearest neighbour was calculated from the set of all locations on the multiline segment positioned closer to the centre of the SI roll. The relative position of the nearest neighbour along the length of the entire multiline segment was used as the longitudinal position. In datasets with atypical morphology, longitudinal axis values for each cell were predicted using a deep neural network trained on a feature space of transcriptional neighbourhood decomposition latent factors and multiline segments marking the base of the basal membrane, the top of each villus and the middle of each villus. Transcriptional neighbourhood decomposition was performed using Scikit-learn71 non-negative matrix factorization on a matrix of the summed transcript count values for the ten nearest neighbours of each cell, calculated with a SciPy72K-dimensional tree, to create a transformed data matrix W with 15 latent factors. To calculate the crypt–villus axis, a fine-tuned Cellpose model was used to segment villi on the basis of WGA staining in Xenium samples and cell spatial positions in MERSCOPE samples. The distance between each cell and the base of the basal membrane was calculated as before, and these values were z-score scaled among cells in the same segmented villus. For datasets with poorly defined morphology, crypt–villus axis values for each cell were predicted using a TensorFlow v2.18.0 (https:// www.tensorflow.org/) deep neural network trained on a feature space comprising a decomposition of latent factors for epithelial and stromal transcriptional neighbourhoods. Transcriptional neighbourhood decomposition was performed by fitting a non-negative matrix factorization model on a matrix of the summed transcript count values (10, mouse; 30, human) for the nearest epithelial and stromal neighbours of each cell in all datasets to avoid the influence of variability in immune populations at different infection states. Crypt–villus axis predictions for each cell were smoothed over their nearest 150 neighbouring cell predictions in human data. To calculate the epithelial axis, the mean distance from each cell to the five nearest epithelial cells was divided by the mean distance to the five nearest cells of any cell type. The resulting values werez-score scaled and clipped at an upper bound to align epithelial distances between the villus and basal membrane.

###### Generation of IMAPs and transcriptional IMAPs

The epithelial IMAP axis values were computed through a biexponential transformation applied to the clipped epithelial axis values across all cells. Each cell was positioned on the IMAP according to its corresponding crypt–villus axis and transformed epithelial axis values. The density in the scattered point cloud was visualized using colour-mapped scipy. stats.gaussian_kde values, with density lines overlaid using seaborn. kdeplot for enhanced clarity and interpretation. Gate boundaries were drawn manually to distinguish the muscularis, villus crypt and villus top by observing the IMAP locations of cell types known to localize to each region. Transcriptional IMAPs were coloured by adding an array of gene expression counts as a point weight parameter to the scipy. stats.gaussian_kde function. Similarly, gene signature IMAPs were coloured using the squared UCell signature enrichment scores as the

point weight parameter. In human IMAPs, signature and gene expression point weights were squared to overcome bias in CD8αβ+ physical density in IMAP visualization.

###### Statistical analysis

In Fig. 2e, significance cut-offs are set at absolute Spearman ρ > 0.05, an arbitrary threshold used to highlight differences between axes. The Spearman coefficients for each gene and their correspondingP values

- are documented in Supplementary Table 3 acrossn = 87,387 P14 T cells. In Extended Data Fig. 7a, the top four differentially expressed genes per condition across P14 cells (n = 4,135 WT,n = 4,161 TGFβR2 knockout) are calculated using Wilcoxon testing with Benjamini–Hochberg correction in the function scanpy.tl.rank_genes_group. In Extended Data Fig. 7d,e,


- a non-parametric two-sample Kolmogorov–Smirnov statistic is used to calculate the significance of the difference between P14 cell type proximity distributions in wild-type and TGFβR2 knockout conditions. A cut-off of similarity is arbitrarily positioned at a Kolmogorov–Smirnov statistic of 0.08, corresponding to a correctedP value of approximately 1 × 10−12 to 1 × 10−10 (Kolmogorov–SmirnovP values vary with the number of samples in the compared distributions). Kolmogorov–Smirnov tests are documented in Supplementary Table 8. In Fig. 4d,f and Extended Data Fig. 1h, gene-expression counts were log-normalized, and two-sample, two-sided t-tests were used to test for significant differences in mean gene expression pairwise between perturbation groups at a significance level of 0.05 and Benjamini–Hochberg correction for P values in each pairwise group. A similar approach was used in Extended Data Fig. 8e using raw detected barcode numbers without normalization. For each subplot in Extended Data Fig. 1g, we applied one-way and two-way analyses of variance, with Dunnett’s method for multiple comparisons. In Extended Data Fig. 1j,k, we used a one-way analysis of variance followed by Tukey’s honestly significant (HSD) difference tests to create confidence intervals. In Extended Data Fig. 9g, human gene expression counts were log-normalized before differentially expressed genes were calculated between human CD8αβ T cells gated to different regions using a two-tailed Wald test in the Python package diffxpy.P values were adjusted using a Benjamini–Hochberg correction. Data are mean ± s.e.m. in all the figures.


###### Cloning and making retrovirus

The LsgC plasmid was generated by using PCR to linearize the backbone of the LsgA plasmid and exclude the Ametrine reporter gene73. NEBuilder HiFi DNA Assembly was then used to insert a HA-tagged mCherry sequence, synthesized by Integrated DNA Technologies (IDT), into the open site. ChopChop was used to design sgRNAs targeting mouseCd19,Thy1 andCxcr3 (ref. 74). Forward (5′-CACCN) and reverse (5′-AAACN) primers forming the sgRNAs were synthesized by IDT. Each sgRNA was assigned a 388-bp or 390-bp barcode, containing seven or eight probe hybridization sites, respectively. These sites corresponded to one of the three lowest-expressed genes in SI P14 CD8 T cells from the SI spatial transcriptomics time course: Muc5ac, Neurog3 and Fer1l6 (Supplementary Table 7). Each 40-bp hybridization site was separated by at least 10 bp containing no homology with the mouse transcriptome. Barcodes were ordered from IDT as gBlocks Gene Fragments in tubes and were cloned into the LsgC vectors on the 3′ side of the mCherry using NEBuilder HiFi DNA Assembly. sgRNAs were inserted into their corresponding LsgC-barcode vector by digesting BbsI restriction sites, followed by room-temperature ligation (T4 DNA ligase, NEB) with the annealed forward and reverse sgRNA primers. LsgC barcodes were transformed into DH5α competent cells (Thermo Fisher). The three unique LsgC barcodes were separately transfected into platinum-E (PlatE) cells (Cell Biolabs, no authentication or mycoplasma contamination test) to make retrovirus. One day before the transfections, 2.5 × 105 PlatE cells were plated on 10-cm dishes in PlatE medium (89% DMEM, 9% FBS, 1% HEPES 1 M, 1% penicillin-streptomycin-glutamine (PSG) (100×, Thermo Fisher) and

0.1% 2-mercaptoethanol (BME)). PlatE cells were transfected using a mix containing 10 µg of LsgC-barcode vector, 5 µg of PCL-Eco (Addgene, 12371) and TransIT-LT1 (Mirus). Retrovirus was collected at 48 h and 72 h after transfection and stored at −80 °C until use.

###### Transductions and spatial transcriptomics with pooled perturbations

One day before transduction, splenic P14 CD8 T cells were isolated from a Cas9–eGFP donor mouse through negative enrichment, and plated in T cell medium (TCM) (89% RPMI, 9% FBS, 1% HEPES 1 M, 1% PSG (100×, Thermo Fisher) and 0.1% BME) containing 1:500 anti-CD3e (Fisher Scientific, 50-112-9591) and CD28 (Fisher Scientific, 50-112-9711) on a six-well plate precoated with 1:30 goat anti-hamster IgG (H+L; Thermo Fisher Scientific) in PBS and stored at 37 °C overnight. Furthermore, an untreated six-well plate was coated with 15 µg ml−1 of retronectin (Takara Bio) in PBS and stored in the dark at 4 °C overnight. During transduction, the retronectin was removed and the plates were coated with TCM and incubated at 37 °C for 30 min. After removal, the three treated plates were coated with a corresponding LsgC-barcode retrovirus over two successive 30-min incubations. Activated cells were resuspended in a 1:1,667 IL-2 in TCM mixture and spread equally across the three retronectin-treated plates. Corresponding retroviruses were added to each well, and the plate was centrifuged at 2,000 rpm for 40 min at 37 °C. The sgRNA knockouts were validated by performing flow cytometry on the transduced cells 2 days after transduction using anti-THY1.2 antibody (30-H12, BioLegend, 1:200 dilution) and anti-CXCR3 antibody (CXCR3-173, eBiosciences, 1:200 dilution) with mCherry+ anti-CD8a+ (53-6.7 BioLegend, 1:200 dilution) cells gated as successfully transduced. One day after transduction, mCherry GFP+ cells were sorted from each of the three transduced populations and pooled 1:1:1, then 1 × 105 cells were transferred into each recipient mouse. Recipient mice were immediately infected with LCMV and euthanized at 7 d.p.i. for spatial transcriptomics.

###### Computational analysis of pooled perturbations in spatial transcriptomics

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


ARI: 0.87 AMI: 0.88
ARI: 0.87 AMI: 0.88| |


|PERSIST (180) NicheNet (158) Immgen (21) Xist (1)|PERSIST (180) NicheNet (158) Immgen (21) Xist (1)|
|---|---|


ARI: 0.72 AMI: 0.76|


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


0.2

1.4

- 3

- 0


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


|r=0.93|


|r=0.95|


|r=0.95|


|r=0.97|


Total counts replica 2

Total counts replica 1

- 102


- 102


- 102


102 103 104 105 106 102 103 104 105 106 102 103 104 105 106

|AMI ARI  350 genes  AMI: 0.88 ARI: 0.86  AMI: 0.85 ARI: 0.83  1000 genes|


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


Cell Count

- 103


CD8αβ T Cells

U 6 8 27 U 6 8 27 U 6 8 27

- 103


CD8αα T Cells

U 6 8 27 U 6 8 27 U 6 8 27 B Cells (B220 Positive)

- 105

- 109


U 6 8 27 U 6 8 27 U 6 8 27

Monocytes

U 6 8 27 U 6 8 27 U 6 8 27 Time p.i. (day)

- 101


CD4 T Cells

U 6 8 27 U 6 8 27 U 6 8 27 γδT Cells

- 103


- 103


U 6 8 27 U 6 8 27 U 6 8 27

Time p.i. (day)

- 102


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

Tuft Vascul

[... text truncated at 100 000 chars ...]