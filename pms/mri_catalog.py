"""Curated 2026-11-15 source check. Guidance is not product test evidence."""
import json
from pathlib import Path

MRDD_URL = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/submission-premarket-notifications-magnetic-resonance-diagnostic-devices"
MR_URL = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/testing-and-labeling-medical-devices-safety-magnetic-resonance-mr-environment"
CLASS_URL = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD_RH/classification.cfm?PCD=LNH"
LAW_URL = "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-892/subpart-B/section-892.1000"
STANDARD_URL = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfStandards/results.cfm?recognitionnumber=12-347&start_search=1"


def catalog():
    extracts = json.loads(Path(__file__).with_name("mri_verified_extracts.json").read_text(encoding="utf-8"))
    definitions = [
        ("mri-lnh", "Nuclear magnetic resonance imaging system — LNH", "classification", CLASS_URL,
         "Classification database snapshot 2026-11-15", ["mri-equipment"],
         "LNH and 21 CFR 892.1000 are classification candidates for an MR diagnostic imaging system, not a determination for image-analysis software.",
         [("Product code LNH", 0)], {}, {"product_code": "LNH", "regulation_number": "892.1000", "related_regulation_key": "mri-8921000"}),
        ("mri-8921000", "21 CFR 892.1000 — Magnetic resonance diagnostic device", "regulation", LAW_URL,
         "eCFR current link checked 2026-11-15; effective revision date unconfirmed", ["mri-equipment"],
         "Identification and Class II classification of magnetic resonance diagnostic devices; RA must confirm applicability to the subject device.",
         [("21 CFR 892.1000(a)-(b)", 0)], {}, {}),
        ("mrdd", "Submission of Premarket Notifications for Magnetic Resonance Diagnostic Devices", "guidance", MRDD_URL,
         "Final — 2023-10-10", ["mri-equipment", "mri-software"],
         "MR diagnostic systems, components and accessories. Software-specific clinical claims and routes need independent RA assessment; scanner classification must not be inherited by standalone ROI analysis.",
         [("II. Scope",5),("III. Relevant Standards",6),("IV.A. Indications for Use",7),("IV.B. Device Description",8),
          ("V. System Safety",11),("VI.A. Performance",12),("VI.B. Safety",13),("VII. Clinical Images",14),("IX. Labeling",17)], extracts["mrdd"], {}),
        ("mr-environment", "Testing and Labeling Medical Devices for Safety in the Magnetic Resonance (MR) Environment", "guidance", MR_URL,
         "Final — 2023-10-10", ["mr-environment"],
         "Devices that might be used in the MR environment. Excludes the MR system and associated components such as accessory spacing pads and coils. RA must determine device-specific hazards and applicability.",
         [("Scope",5),("Relevant Consensus Standards",7),("Magnetically Induced Displacement Force",9),
          ("Magnetically Induced Torque",10),("Heating",11),("Medical Device Malfunction",15),
          ("Extent of Image Artifact",17),("Reporting Results",18),("MRI Safety Labeling",19),
          ("Appendix 1. Test Result Summary",28),("Appendix 2. MR Conditional Labeling Examples",29)], extracts["mr-environment"], {}),
        ("mri-iec-60601-2-33", "IEC 60601-2-33 — FDA recognition candidate 12-347", "standard", STANDARD_URL,
         "Edition 4.0 2022-08 — search index checked 2026-11-15", ["mri-equipment"],
         "MR diagnostic equipment basic safety and essential performance. Recognition detail, transition dates and subject-product applicability require RA confirmation.",
         [("FDA recognition 12-347 search record",0)], {}, {"standard_number":"IEC 60601-2-33", "edition":"Edition 4.0 2022-08",
          "recognition_number":"12-347", "recognition_scope":"Complete in official search index; detailed limitations RA 확인 필요"}),
    ]
    sources = []
    for key,title,kind,url,version,types,scope,sections,pages,metadata in definitions:
        guidance = kind == "guidance"
        sources.append(dict(key=key,title=title,source_type=kind,official_url=url,document_version=version,
            checked_on="2026-11-15",issued_on=("2016-11-18" if key == "mrdd" else "2021-05-20" if key == "mr-environment" else None),
            revised_on="2023-10-10" if guidance else None,
            pdf_url="https://www.fda.gov/media/" + ("92921" if key == "mrdd" else "74201") + "/download" if guidance else "",
            device_types=types,scope=scope,sections=[dict(clause=c,page=p) for c,p in sections],pages=pages,
            metadata={**metadata, "verification_method":"Official FDA/eCFR pages and official PDF text via web reader",
                      "hash_kind":"SHA-256 of stored record/text; not original PDF bytes"},
            retrieval_status="verified_text" if guidance else "metadata_only",
            failure_reason="Direct PDF fetch returned HTTP 404; verified web-reader text retained, PDF byte hash unavailable" if guidance else
                           "Full source body not collected; use official link. Detailed standard record fetch unavailable" if kind == "standard" else "Full source body not collected; official metadata only"))
    return sources


def templates():
    def item(id,title,key,clause,page,**extra):
        return dict(id=id,title=title,condition="always",evidence_type="Product specification / test report / labeling",
                    source_key=key,source_section=clause,page=page,draft_section=title,
                    mapping="RA confirmation required — no automatic submission mapping",**extra)
    equipment = [item("MRI.USE","Intended use and classification candidate","mrdd","IV.A. Indications for Use",7),
        item("MRI.SPEC","System specification and field strength","mrdd","IV.B. Device Description",8),
        item("MRI.COIL","Coils, accessories and operating modes","mrdd","IV.B. Device Description",8),
        item("MRI.IMG","Image quality and performance","mrdd","VI.A. Performance",12,test_required=True),
        item("MRI.SAFE","System safety testing","mrdd","VI.B. Safety",13,test_required=True),
        item("MRI.CLIN","Clinical image evidence","mrdd","VII. Clinical Images",14),
        item("MRI.LABEL","Labeling and user manual","mrdd","IX. Labeling",17),
        item("MRI.STD","Applicable recognized standards","mrdd","III. Relevant Standards",6)]
    software = [item("SW.USE","Research output versus clinical claims / intended use","mrdd","II. Scope",5),
        item("SW.INPUT","Input compatibility / MRI versus ROI table / formats","mrdd","II. Scope",5),
        item("SW.PRE","Preprocessing and input validation","mrdd","II. Scope",5),
        item("SW.ALG","Algorithm and software/model validation","mrdd","II. Scope",5),
        item("SW.DATA","Separated development and evaluation data","mrdd","II. Scope",5),
        item("SW.METRIC","Performance metrics and evidence","mrdd","II. Scope",5,test_required=True),
        item("SW.FAIL","Failure and exclusion conditions","mrdd","II. Scope",5)]
    environment = [item("MR.USE","Device type and conditions of MR use","mr-environment","Scope",5),
        item("MR.FORCE","Displacement and torque hazards","mr-environment","Magnetically Induced Displacement Force",9,test_required=True),
        item("MR.HEAT","RF/gradient heating evidence","mr-environment","Heating",11,test_required=True),
        item("MR.FUNC","Device function in MR conditions","mr-environment","Medical Device Malfunction",15,test_required=True),
        item("MR.ART","Image artifacts","mr-environment","Extent of Image Artifact",17,test_required=True),
        item("MR.LABEL","Tested conditions versus MR label conditions","mr-environment","MRI Safety Labeling",19,compare_label=True)]
    result=[]
    for key,name,url,items,fields,conditions in [
        ("mri-equipment","MRI imaging equipment",MRDD_URL,equipment,
         {"field_strength":"Static magnetic field strength / original unit", "coils":"Coils and accessories", "modes":"Acquisition / operating modes",
          "configuration":"Applicant model configuration", "software":"Software version"},
         {"scope":"mri-equipment","product_codes":["LNH"],"regulations":["892.1000"],"candidate_code":"LNH"}),
        ("mri-software","MRI image / ROI analysis software — evidence collection",MRDD_URL,software,
         {"clinical_claim":"Medical / research claims", "inputs":"Raw MRI or derived ROI volume table", "raw_mri_processing":"Does software process original MRI?",
          "outputs":"Research output versus clinical output", "formats":"Supported formats", "software":"Software version", "algorithm_version":"Model / algorithm version",
          "preprocessing":"Preprocessing", "data_split":"Development / validation / test split", "metrics":"Performance metrics", "failure_conditions":"Failure / exclusion conditions"},
         {"scope":"mri-software","internal_collection":True}),
        ("mr-environment","Device used in the MR environment",MR_URL,environment,
         {"device_type":"Device type", "use_conditions":"MR intended use conditions", "configuration":"Applicant device configuration",
          "label_conditions":"Conditions stated in MR labeling", "software":"Software version / not applicable"},
         {"scope":"mr-environment","internal_collection":True})]:
        result.append(dict(key=key,version=1,name=name,market="US",pathway="RA confirmation required",state="PUBLISHED",example=False,
            source_url=url,issued_on="2023-10-10",checked_on="2026-11-15",fields=fields,items=items,
            conditions={**conditions,"include":"RA must determine subject-device scope and applicability",
                        "exclude":"No automatic classification, clearance or substantial equivalence determination"}))
    return result
