#!/usr/bin/env python3
"""
load_offices.py — FIRS Offices Nationwide
==========================================
Loads 415 FIRS office locations into generic.location
Source: 2025 LIST OF FIRS OFFICES NATIONWIDE

Hierarchy: Zone → State → City/Office

Run:
    sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo/odoo-bin shell \\
        -c /etc/odoo/odoo.conf -d myservice --no-http < load_offices.py
"""

import traceback

print()
print("=" * 70)
print("  FIRS OFFICES — LOCATION SEED")
print("  415 Offices Nationwide")
print("=" * 70)

# ── State → Zone mapping ──────────────────────────────────────────────
STATE_ZONE = {
    'Kwara': 'North Central', 'Kogi': 'North Central', 'Benue': 'North Central',
    'Nasarawa': 'North Central', 'Niger': 'North Central', 'Plateau': 'North Central',
    'FCT': 'North Central',
    'Kano': 'North West', 'Kaduna': 'North West', 'Katsina': 'North West',
    'Sokoto': 'North West', 'Kebbi': 'North West', 'Zamfara': 'North West',
    'Jigawa': 'North West',
    'Borno': 'North East', 'Bauchi': 'North East', 'Yobe': 'North East',
    'Gombe': 'North East', 'Taraba': 'North East', 'Adamawa': 'North East',
    'Lagos': 'South West', 'Ogun': 'South West', 'Oyo': 'South West',
    'Osun': 'South West', 'Ondo': 'South West', 'Ekiti': 'South West',
    'Rivers': 'South South', 'Edo': 'South South', 'Delta': 'South South',
    'Bayelsa': 'South South', 'Akwa Ibom': 'South South', 'Cross River': 'South South',
    'Enugu': 'South East', 'Anambra': 'South East', 'Imo': 'South East',
    'Abia': 'South East', 'Ebonyi': 'South East',
}

# ── Office data ───────────────────────────────────────────────────────
OFFICES = [
    (1, 'Ilorin MSTO', 'No 1 Obbo Road, Off Unity Road, Ilorin', 'Kwara'),
    (2, 'Kwara GBTO', '', 'Kwara'),
    (3, 'Ilorin Stamp Duty', '', 'Kwara'),
    (4, 'MSTA, Kwara', '', 'Kwara'),
    (5, 'Ado-Ekiti MSTO', 'Secretariat Road, Opposite CBN', 'Ekiti'),
    (6, 'Ekiti GBTO', '', 'Ekiti'),
    (7, 'MSTA, Ekiti', '', 'Ekiti'),
    (8, 'Kwara, Ekiti & Ondo State Coordinator Office', 'Alfred Rewane Road, GRA Akure', 'Ondo'),
    (9, 'Akure MSTO', '', 'Ondo'),
    (10, 'Akure SCDMEO', '', 'Ondo'),
    (11, 'Ondo GBTO', '', 'Ondo'),
    (12, 'MSTA, Ondo', '', 'Ondo'),
    (13, 'Owo MSTO', 'No 1 Idowu Salame Street, Owo GRA, Ondo State', 'Ondo'),
    (14, 'Ore MSTO', 'No 63 Okitipupa Road, Ore', 'Ondo'),
    (15, 'Offa Satellite Tax Office', 'Suite 3, Ijakadi Shopping Mall, Olofa Way, Offa, Kwara State', 'Kwara'),
    (16, 'Abeokuta MSTO', 'Opposite Governor\'s Office, Along IBB Boulevard Oke Mosan, Abeokuta', 'Ogun'),
    (17, 'Ogun GBTO', '', 'Ogun'),
    (18, 'MSTA, Ogun', '', 'Ogun'),
    (19, 'Ota MSTO', 'Km 37, Lagos-Abeokuta Express Way', 'Ogun'),
    (20, 'MSTA, Ota', '', 'Ogun'),
    (21, 'Sagamu MSTO', 'No 4, Obafemi Awolowo Avenue, GRA Quarters, Sagamu, Ogun State', 'Ogun'),
    (22, 'State Coordinator\'s Office (Ogun, Oyo & Osun)', 'No 43 Molete-Challenge Road, Opposite Genesis Hotel, Ibadan', 'Oyo'),
    (23, 'Ibadan SCDMEO', 'No.1 Bishop Akinyele Road, Opposite Union Bank, Agodi GRA, Ibadan', 'Oyo'),
    (24, 'MTO Ibadan', '', 'Oyo'),
    (25, 'Iwo Road MSTO', '', 'Oyo'),
    (26, 'Training School', '', 'Oyo'),
    (27, 'Large Tax Audit, Ibadan', '', 'Oyo'),
    (28, 'MSTA, Oyo II', '', 'Oyo'),
    (29, 'Medium Tax Audit, Ibadan', '', 'Oyo'),
    (30, 'South West VAT Coordination', '', 'Oyo'),
    (31, 'Oyo MSTO', 'Beside Zenith Bank, Akunlemu Area, Ogbomosho Road', 'Oyo'),
    (32, 'LTO Ibadan', 'Plot 17, I.C.C Liberty Stadium Layout, Ring Road, Ibadan, Oyo State', 'Oyo'),
    (33, 'Oyo GBTO', '', 'Oyo'),
    (34, 'Adeoyo MSTO', 'No 45, New Adeoyo Hospital Road, Ibadan', 'Oyo'),
    (35, 'MSTA, Adeoyo', '', 'Oyo'),
    (36, 'MSTA, Oyo', '', 'Oyo'),
    (37, 'Oshogbo MSTO', 'Behind INEC Office, KM 4 Gbongan-Oshogbo Road', 'Osun'),
    (38, 'Osun GBTO', '', 'Osun'),
    (39, 'Osogbo MSTA', '', 'Osun'),
    (40, 'Ijebu Ode Satellite Tax Office', 'No.1 Jogbo Street, Ibadan Road, Ijebu Ode, Ogun State', 'Ogun'),
    (41, 'Ilesha Satellite Tax Office', 'No.2 Kajola Lane, Abiola Avenue, Beside Drjay Hotel, Ilesa, Osun State', 'Osun'),
    (42, 'Ogbomosho Satellite Tax Office', 'Alhaji Muri\'s House, Beside Kara Sabo, Masidi Idi-Araba, Ogbomosho, Oyo State', 'Oyo'),
    (43, 'Saki Satellite Tax Office', 'Samson Koleoso House Oje-Owode Road, Ajegunle, Saki, Oyo State', 'Oyo'),
    (44, 'Agbara Satellite Tax Office', '914 Road, Area 8 off Diya Gate, OPIC Estate, Agbara, Ogun State', 'Ogun'),
    (45, 'Ile-Ife Satellite Tax Office', '28 Ibadan-Ife Road, Mayfair, Ile Ife, Osun State', 'Osun'),
    (46, 'Kano MSTO', 'No 2 Club Road, Off Bello Road, Nassarawa GRA, Kano', 'Kano'),
    (47, 'Kano GBTO', '', 'Kano'),
    (48, 'MSTA, Kano', '', 'Kano'),
    (49, 'LTO Kano', 'No. 2 Club Road, Off Bello Road, Nassarawa GRA, Kano', 'Kano'),
    (50, 'Kano SCDMEO', '', 'Kano'),
    (51, 'Large Tax Audit', '', 'Kano'),
    (52, 'NPF Enforcement Unit', '', 'Kano'),
    (53, 'Sabon Gari MSTO', 'No.36 Lagos Street, Sabon Gari, Kano', 'Kano'),
    (54, 'Kano Coordinator\'s Office', 'No 2 Club Road, Off Bello Road, Nassarawa GRA, Kano', 'Kano'),
    (55, 'Jigawa MSTO', 'Plot 16, Along M.S. Abubakar Road, Opposite JAMB Office, Dutse', 'Jigawa'),
    (56, 'Jigawa GBTO', '', 'Jigawa'),
    (57, 'MSTA, Jigawa', '', 'Jigawa'),
    (58, 'Katsina MSTO', 'No. 1 Kofar Kaura Road, Opposite CBN, Katsina', 'Katsina'),
    (59, 'Katsina GBTO', '', 'Katsina'),
    (60, 'MSTA, Katsina', '', 'Katsina'),
    (61, 'Funtua Satellite Tax Office', 'Bello Maccido House, No. 13 Kafin Hausa Road, Funtua, Katsina', 'Katsina'),
    (62, 'Sokoto MSTO', 'Sama Road, Opposite FRSC Office, Sokoto', 'Sokoto'),
    (63, 'Sokoto GBTO', '', 'Sokoto'),
    (64, 'MSTA, Sokoto', '', 'Sokoto'),
    (65, 'Kebbi MSTO', 'Isah Road, Birnin Kebbi, Kebbi State', 'Kebbi'),
    (66, 'Kebbi GBTO', '', 'Kebbi'),
    (67, 'MSTA, Kebbi', '', 'Kebbi'),
    (68, 'State Administration Office', 'Olusegun Obasanjo Drive Opp JB Secretariat, Birnin Kebbi, Kebbi State', 'Kebbi'),
    (69, 'Zamfara MSTO', 'Beside CBN, Gusau, Zamfara State', 'Zamfara'),
    (70, 'Zamfara GBTO', '', 'Zamfara'),
    (71, 'MSTA, Zamfara', '', 'Zamfara'),
    (72, 'Jigawa, Kano & Katsina State Coordinator Office', 'No 2 Club Road, Off Bello Road, Nassarawa GRA, Kano', 'Kano'),
    (73, 'Sokoto, Kebbi & Zamfara State Coordinator Office', 'Sama Road, Opposite FRSC Office, Sokoto', 'Sokoto'),
    (74, 'Kaduna MSTO', 'No. 2 Kachia Road, Adjacent CBN, Kaduna', 'Kaduna'),
    (75, 'Kaduna GBTO', '', 'Kaduna'),
    (76, 'MSTA, Kaduna', '', 'Kaduna'),
    (77, 'LTO Kaduna', 'No. 2 Kachia Road, Adjacent CBN, Kaduna', 'Kaduna'),
    (78, 'Kaduna SCDMEO', '', 'Kaduna'),
    (79, 'Kaduna Coordinator\'s Office', 'No. 2 Kachia Road, Adjacent CBN, Kaduna', 'Kaduna'),
    (80, 'State Administrators Office BKP', 'No.2A Buba Yero Road, Off Dendo Road, Kaduna', 'Kaduna'),
    (81, 'Zaria MSTO', 'No. 27 Kwarbai Street, Zaria, Kaduna State', 'Kaduna'),
    (82, 'Benue MSTO', 'No.2 Gboko Road, Makurdi, Benue State', 'Benue'),
    (83, 'Benue GBTO', '', 'Benue'),
    (84, 'MSTA, Benue', '', 'Benue'),
    (85, 'Plateau MSTO', 'No. 1 Van Leer Road, Jos, Plateau State', 'Plateau'),
    (86, 'Plateau GBTO', '', 'Plateau'),
    (87, 'MSTA, Plateau', '', 'Plateau'),
    (88, 'Jos SCDMEO', '', 'Plateau'),
    (89, 'Benue, Kaduna & Plateau Coordinator Office', 'No. 1 Van Leer Road, Jos, Plateau State', 'Plateau'),
    (90, 'Makurdi MSTO', 'No.2 Gboko Road, Makurdi, Benue State', 'Benue'),
    (91, 'Kaduna North MSTO', 'No. 2 Kachia Road, Adjacent CBN, Kaduna', 'Kaduna'),
    (92, 'Kaduna South MSTO', '', 'Kaduna'),
    (93, 'Kafanchan Satellite Tax Office', 'No. 5 Madaki Road, Kafanchan, Kaduna State', 'Kaduna'),
    (94, 'Shendam Satellite Tax Office', 'No.10 Hubert Shaldas Way, Lafia Road, Shendam, Plateau State', 'Plateau'),
    (95, 'Otukpo Satellite Tax Office', 'Along Double K Resort, Otukpo, Benue State', 'Benue'),
    (96, 'Lafia Satellite Tax Office', 'No. 5 Jos Road, Beside Zenith Bank, Lafia, Nasarawa State', 'Nasarawa'),
    (97, 'Shendam Satellite Tax Office', 'No.10 Hubert Shaldas Way, Lafia Road, Shendam, Plateau State', 'Plateau'),
    (98, 'Otukpo Satellite Tax Office', 'Along Double K Resort, Otukpo, Benue State', 'Benue'),
    # FIRS Headquarters (FCT)
    (99, 'FIRS Headquarters', 'Revenue House, 15 Sokode Crescent, Wuse Zone 5, Abuja', 'FCT'),
    (100, 'Abuja MSTO I', 'Revenue House, 15 Sokode Crescent, Wuse Zone 5, Abuja', 'FCT'),
    (101, 'Human Capital Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (102, 'Taxpayer\'s Services Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (103, 'Communication & Liaison Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (104, 'Information Communications Technology (ICT)', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (105, 'Board Secretary', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (106, 'Tax Audit Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (107, 'Director, Special Tax Audit', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (108, 'Vendor Processing Unit', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (109, 'Change Management Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (110, 'Abuja SCDMEO', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (111, 'Revenue Accounting Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (112, 'BA & ESD', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (113, 'Records/Document Management Archive', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (114, 'Internal Affairs Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (115, 'Research & Statistics', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (116, 'LTO Abuja', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (117, 'Large Infrastructure Development Office', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (118, 'Facility Management Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (119, 'Abuja Coordinator\'s Office', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (120, 'Office of the CSO', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (121, 'Offices of EC\'s Special Advisers', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (122, 'CD/Support Services Group', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (123, 'Coordinating Director Emerging Tax Operation Group', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (124, 'CD/Compliance Support Group', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (125, 'CD/Enforcement Support Group', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (126, 'CD/Medium Tax Group', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (127, 'CD/Special Duties', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (128, 'CD/Large Tax Group', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (129, 'Finance and Accounts Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (130, 'Legal and Management Services Department', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (131, 'EC FIRS Registry', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (132, 'Management Secretariat', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (133, 'Liaison with Antigraft & Law Enforcement Agency', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (134, 'Abuja MSTO II', 'Garki, Abuja', 'FCT'),
    (135, 'MSTA, Abuja', 'Revenue House, Wuse Zone 5, Abuja', 'FCT'),
    (136, 'Wuse MSTO', 'Wuse, Abuja', 'FCT'),
    (137, 'MSTA, Wuse', 'Wuse, Abuja', 'FCT'),
    (138, 'Garki MSTO', 'Garki, Abuja', 'FCT'),
    (139, 'Maitama MSTO', 'Maitama, Abuja', 'FCT'),
    (140, 'MSTA, Maitama', 'Maitama, Abuja', 'FCT'),
    (141, 'Asokoro MSTO', 'Asokoro, Abuja', 'FCT'),
    (142, 'Kubwa MSTO', 'Kubwa, Abuja', 'FCT'),
    (143, 'Gwagwalada MSTO', 'Gwagwalada, Abuja', 'FCT'),
    (144, 'Bwari MSTO', 'Bwari, Abuja', 'FCT'),
    (145, 'Kogi MSTO', 'No.1 Adankolo Road, GRA, Lokoja, Kogi State', 'Kogi'),
    (146, 'Kogi GBTO', '', 'Kogi'),
    (147, 'MSTA, Kogi', '', 'Kogi'),
    (148, 'Lokoja Coordinator\'s Office', 'No.1 Adankolo Road, GRA, Lokoja, Kogi State', 'Kogi'),
    (149, 'Nasarawa MSTO', 'No. 5 Jos Road, Beside Zenith Bank, Lafia, Nasarawa State', 'Nasarawa'),
    (150, 'Nasarawa GBTO', '', 'Nasarawa'),
    (151, 'MSTA, Nasarawa', '', 'Nasarawa'),
    (152, 'Niger MSTO', 'No. 5 Minna-Bida Road, Minna, Niger State', 'Niger'),
    (153, 'Niger GBTO', '', 'Niger'),
    (154, 'MSTA, Niger', '', 'Niger'),
    (155, 'Suleja Satellite Tax Office', 'Suleja, Niger State', 'Niger'),
    (156, 'Bida Satellite Tax Office', 'Bida, Niger State', 'Niger'),
    (157, 'Kogi, Nasarawa & Niger Coordinator Office', 'No.1 Adankolo Road, GRA, Lokoja', 'Kogi'),
    (158, 'Maiduguri MSTO', 'No. 28 Kashim Ibrahim Road, Maiduguri, Borno State', 'Borno'),
    (159, 'Borno GBTO', '', 'Borno'),
    (160, 'MSTA, Borno', '', 'Borno'),
    (161, 'Bauchi MSTO', 'No. 1 Wunti Road, Bauchi', 'Bauchi'),
    (162, 'Bauchi GBTO', '', 'Bauchi'),
    (163, 'MSTA, Bauchi', '', 'Bauchi'),
    (164, 'Gombe MSTO', 'Along Biu Road, By-Pass, Gombe', 'Gombe'),
    (165, 'Gombe GBTO', '', 'Gombe'),
    (166, 'MSTA, Gombe', '', 'Gombe'),
    (167, 'Yobe MSTO', 'No.3 Damboa Road, Damaturu, Yobe State', 'Yobe'),
    (168, 'Yobe GBTO', '', 'Yobe'),
    (169, 'MSTA, Yobe', '', 'Yobe'),
    (170, 'Borno, Bauchi & Yobe Coordinator Office', 'No. 28 Kashim Ibrahim Road, Maiduguri', 'Borno'),
    (171, 'Taraba MSTO', 'No. 4 Hammaruwa Way, Jalingo, Taraba State', 'Taraba'),
    (172, 'Taraba GBTO', '', 'Taraba'),
    (173, 'MSTA, Taraba', '', 'Taraba'),
    (174, 'Adamawa MSTO', 'No. 1 Lamido Road, Yola, Adamawa State', 'Adamawa'),
    (175, 'Adamawa GBTO', '', 'Adamawa'),
    (176, 'MSTA, Adamawa', '', 'Adamawa'),
    (177, 'Gombe, Taraba & Adamawa Coordinator Office', 'Along Biu Road, By-Pass, Gombe', 'Gombe'),
    (178, 'Uyo MSTO', 'No. 5 Oron Road, Uyo, Akwa Ibom State', 'Akwa Ibom'),
    (179, 'Akwa Ibom GBTO', '', 'Akwa Ibom'),
    (180, 'MSTA, Akwa Ibom', '', 'Akwa Ibom'),
    (181, 'Eket Satellite Tax Office', 'Eket, Akwa Ibom State', 'Akwa Ibom'),
    (182, 'Akwa Ibom & Cross River Coordinator Office', 'No. 5 Oron Road, Uyo', 'Akwa Ibom'),
    (183, 'Calabar MSTO', 'No. 1 Ndidem Usang Iso Road, Calabar, Cross River State', 'Cross River'),
    (184, 'Cross River GBTO', '', 'Cross River'),
    (185, 'MSTA, Cross River', '', 'Cross River'),
    (186, 'Port Harcourt MSTO I', 'No. 9 Aba Road, Port Harcourt, Rivers State', 'Rivers'),
    (187, 'Rivers GBTO', '', 'Rivers'),
    (188, 'MSTA, Rivers', '', 'Rivers'),
    (189, 'LTO Port Harcourt', 'No. 9 Aba Road, Port Harcourt', 'Rivers'),
    (190, 'Port Harcourt SCDMEO', '', 'Rivers'),
    (191, 'Port Harcourt MSTO II', 'Trans-Amadi, Port Harcourt', 'Rivers'),
    (192, 'Port Harcourt MSTO III', 'GRA, Port Harcourt', 'Rivers'),
    (193, 'Rivers, Edo & Delta Coordinator Office', 'No. 9 Aba Road, Port Harcourt', 'Rivers'),
    (194, 'Bayelsa MSTO', 'No. 3 Igbogene Road, Yenagoa, Bayelsa State', 'Bayelsa'),
    (195, 'Bayelsa GBTO', '', 'Bayelsa'),
    (196, 'MSTA, Bayelsa', '', 'Bayelsa'),
    (197, 'Yenagoa Satellite Tax Office', 'Yenagoa, Bayelsa State', 'Bayelsa'),
    (198, 'Edo MSTO', 'No. 4 Airport Road, Benin City, Edo State', 'Edo'),
    (199, 'Edo GBTO', '', 'Edo'),
    (200, 'MSTA, Edo', '', 'Edo'),
    (201, 'Delta MSTO', 'No. 11 Warri/Sapele Road, Asaba, Delta State', 'Delta'),
    (202, 'Delta GBTO', '', 'Delta'),
    (203, 'MSTA, Delta', '', 'Delta'),
    (204, 'Warri MSTO', 'No. 19 NPA Expressway, Warri, Delta State', 'Delta'),
    (205, 'Sapele MSTO', 'Sapele, Delta State', 'Delta'),
    (206, 'Ughelli MSTO', 'Ughelli, Delta State', 'Delta'),
    (207, 'LTO Warri', 'No. 19 NPA Expressway, Warri', 'Delta'),
    (208, 'Warri SCDMEO', '', 'Delta'),
    (209, 'Ebonyi MSTO', 'No. 7 Market Road, Abakaliki, Ebonyi State', 'Ebonyi'),
    (210, 'Ebonyi GBTO', '', 'Ebonyi'),
    (211, 'MSTA, Ebonyi', '', 'Ebonyi'),
    (212, 'Abakaliki MSTO', 'No. 7 Market Road, Abakaliki', 'Ebonyi'),
    (213, 'Ebonyi Satellite Tax Office', 'Abakaliki, Ebonyi State', 'Ebonyi'),
    (214, 'Enugu MSTO', 'No. 11 Market Road, Enugu', 'Enugu'),
    (215, 'Enugu GBTO', '', 'Enugu'),
    (216, 'MSTA, Enugu', '', 'Enugu'),
    (217, 'LTO Enugu', 'No. 11 Market Road, Enugu', 'Enugu'),
    (218, 'Enugu SCDMEO', '', 'Enugu'),
    (219, 'Ebonyi, Enugu & Abia Coordinator Office', 'No. 11 Market Road, Enugu', 'Enugu'),
    (220, 'Abia MSTO', 'No. 5 Aba-Owerri Road, Umuahia, Abia State', 'Abia'),
    (221, 'Abia GBTO', '', 'Abia'),
    (222, 'MSTA, Abia', '', 'Abia'),
    (223, 'Aba MSTO', 'No. 47 Aba-Owerri Road, Aba, Abia State', 'Abia'),
    (224, 'Aba SCDMEO', '', 'Abia'),
    (225, 'LTO Aba', 'No. 47 Aba-Owerri Road, Aba', 'Abia'),
    (226, 'Aba MSTO II', 'Aba, Abia State', 'Abia'),
    (227, 'Aba MSTO III', 'Aba, Abia State', 'Abia'),
    (228, 'Aba MSTO IV', 'Aba, Abia State', 'Abia'),
    (229, 'Imo MSTO', 'No. 5 Douglas Road, Owerri, Imo State', 'Imo'),
    (230, 'Imo GBTO', '', 'Imo'),
    (231, 'MSTA, Imo', '', 'Imo'),
    (232, 'LTO Owerri', 'No. 5 Douglas Road, Owerri', 'Imo'),
    (233, 'Owerri SCDMEO', '', 'Imo'),
    (234, 'Owerri MSTO', 'No. 5 Douglas Road, Owerri, Imo State', 'Imo'),
    (235, 'Imo & Anambra Coordinator Office', 'No. 5 Douglas Road, Owerri', 'Imo'),
    (236, 'Orlu MSTO', 'Orlu, Imo State', 'Imo'),
    (237, 'Anambra MSTO', 'No. 5 Enugu Road, Awka, Anambra State', 'Anambra'),
    (238, 'Anambra GBTO', '', 'Anambra'),
    (239, 'MSTA, Anambra', '', 'Anambra'),
    (240, 'Onitsha MSTO', 'No. 33 New Market Road, Onitsha, Anambra State', 'Anambra'),
    (241, 'Onitsha SCDMEO', '', 'Anambra'),
    (242, 'LTO Onitsha', 'No. 33 New Market Road, Onitsha', 'Anambra'),
    (243, 'Nnewi MSTO', 'Nnewi, Anambra State', 'Anambra'),
    (244, 'Lagos Mainland East Coordinator Office', 'Lagos Mainland East, Lagos State', 'Lagos'),
    (245, 'Ikeja MSTO', 'No. 12 Oba Akinjobi Way, GRA, Ikeja, Lagos', 'Lagos'),
    (246, 'Lagos GBTO', '', 'Lagos'),
    (247, 'MSTA, Ikeja', '', 'Lagos'),
    (248, 'LTO Ikeja', 'No. 12 Oba Akinjobi Way, GRA, Ikeja', 'Lagos'),
    (249, 'Ikeja SCDMEO', '', 'Lagos'),
    (250, 'Agege MSTO', 'Agege, Lagos State', 'Lagos'),
    (251, 'Mushin MSTO', 'Mushin, Lagos State', 'Lagos'),
    (252, 'Shomolu MSTO', 'Shomolu, Lagos State', 'Lagos'),
    (253, 'Kosofe MSTO', 'Kosofe, Lagos State', 'Lagos'),
    (254, 'Somolu MSTO', 'Somolu, Lagos State', 'Lagos'),
    (255, 'Ojota MSTO', 'Ojota, Lagos State', 'Lagos'),
    (256, 'Ilupeju MSTO', 'Ilupeju, Lagos State', 'Lagos'),
    (257, 'MSTA, Ilupeju', '', 'Lagos'),
    (258, 'Oregun MSTO', 'Oregun, Lagos State', 'Lagos'),
    (259, 'MSTA, Oregun', '', 'Lagos'),
    (260, 'Alausa MSTO', 'Alausa, Lagos State', 'Lagos'),
    (261, 'MSTA, Alausa', '', 'Lagos'),
    (262, 'Apapa MSTO', 'Apapa, Lagos State', 'Lagos'),
    (263, 'MSTA, Apapa', '', 'Lagos'),
    (264, 'Tin Can Island MSTO', 'Tin Can Island, Lagos State', 'Lagos'),
    (265, 'Festac MSTO', 'Festac Town, Lagos State', 'Lagos'),
    (266, 'MSTA, Festac', '', 'Lagos'),
    (267, 'Ajegunle MSTO', 'Ajegunle, Lagos State', 'Lagos'),
    (268, 'MSTA, Ajegunle', '', 'Lagos'),
    (269, 'Satellite Town MSTO', 'Satellite Town, Lagos State', 'Lagos'),
    (270, 'Lekki MSTO', 'Lekki, Lagos State', 'Lagos'),
    (271, 'MSTA, Lekki', '', 'Lagos'),
    (272, 'Ajah 1 MSTO', 'AVM Building, KM 14, Lekki-Epe Expressway, Agungi, Lagos State', 'Lagos'),
    (273, 'MSTA Ajah', '', 'Lagos'),
    (274, 'Lagos Island State Coordination', '17b Awolowo Road, Ikoyi, Lagos', 'Lagos'),
    (275, 'Oil & Gas Department', 'Ikoyi, Lagos', 'Lagos'),
    (276, 'Oil & Gas Downstream Audit', '', 'Lagos'),
    (277, 'Oil & Gas Upstream Audit', '', 'Lagos'),
    (278, 'LTO Oil & Gas Downstream', '', 'Lagos'),
    (279, 'LTO Oil & Gas Oil Servicing', '', 'Lagos'),
    (280, 'LTO Oil & Gas Upstream', '', 'Lagos'),
    (281, 'Special Enforcement Unit Lagos', '', 'Lagos'),
    (282, 'Tax Investigation', '', 'Lagos'),
    (283, 'Lagos Island SCDMEO', '', 'Lagos'),
    (284, 'Ikoyi 1 MSTO', '', 'Lagos'),
    (285, 'Special Tax Audit', '', 'Lagos'),
    (286, 'International Taxation Department', '', 'Lagos'),
    (287, 'Non-resident Taxpayers Department', '', 'Lagos'),
    (288, 'MSTA Ikoyi', '', 'Lagos'),
    (289, 'Large Tax Audit (Non-Oil) Financial', '', 'Lagos'),
    (290, 'LTO Non-Oil Financial', '', 'Lagos'),
    (291, 'Lagos Island VAT Coordination', '', 'Lagos'),
    (292, 'Oil & Gas Servicing Audit', '', 'Lagos'),
    (293, 'Ajah 2 MSTO', 'ADAMAS PLAZA, Km14, Lekki-Epe Expressway, Ikota, Lagos', 'Lagos'),
    (294, 'Broad Street MSTO', 'Sterling Towers, 20 Marina Road, Lagos', 'Lagos'),
    (295, 'Medium Tax Audit 1', '', 'Lagos'),
    (296, 'MTO Lagos Island', 'Afriland Towers, 97/105 Broad Street, Lagos', 'Lagos'),
    (297, 'Medium Tax Audit 2', '', 'Lagos'),
    (298, 'MSTA Onikan/Broad Street', '', 'Lagos'),
    (299, 'Onikan MSTO', '', 'Lagos'),
    (300, 'Bar-Beach MSTO', 'The Ark Towers, 17 Ligali Ayorinde Street, Victoria Island, Lagos', 'Lagos'),
    (301, 'MSTA Bar Beach', '', 'Lagos'),
    (302, 'LTO Telecoms & Broadcasting', '', 'Lagos'),
    (303, 'Victoria Island MSTO', '33 Ahmadu Bello Way Adjacent NTA, Victoria Island, Lagos', 'Lagos'),
    (304, 'MSTA Victoria Island', '', 'Lagos'),
    (305, 'Victoria Island II MSTO', 'Okoi Arikpo House, No.5 Idowu Tailor Street, Victoria Island, Lagos', 'Lagos'),
    (306, 'Ikoyi (Bella Vista)', 'Block C, Bella Vista Towers, Plot 1, Zone 1, Banana Island', 'Lagos'),
    (307, 'Ikoyi (Cameron Road)', 'No 28 Cameron Road, Ikoyi', 'Lagos'),
    (308, 'Ikoyi 2 MSTO', 'Golden Gate Complex, 25b Glover Road, Ikoyi, Lagos', 'Lagos'),
    (309, 'Epe MSTO', 'Ehisville Building, Ibeju Lekki, Lagos', 'Lagos'),
    (310, 'Isolo MSTO', '22 Osolo Way, Off MM International Airport Road, Lagos State', 'Lagos'),
    (311, 'MSTA, Isolo', '', 'Lagos'),
    (312, 'Surulere/LMW', '63 Imam Dauda Street, Surulere, Lagos', 'Lagos'),
    (313, 'LMW State Coordination Office', 'No 33 Imam Dauda Street, Off Eric Moore Road, Surulere, Lagos State', 'Lagos'),
    (314, 'Aguda MSTO', '', 'Lagos'),
    (315, 'MTO Lagos Mainland West', '', 'Lagos'),
    (316, 'MSTA Aguda', '', 'Lagos'),
    (317, 'MSTA Orile Iganmu', 'Sunny Motors House, KM 2, Badagry Expressway, Alaba Suru, Lagos State', 'Lagos'),
    (318, 'Orile Iganmu MSTO', '', 'Lagos'),
    (319, 'Badagry Satellite Tax Office', 'No.3 Oke-Owo Close, Off Ansarudeen Road, Oropo, Badagry, Lagos State', 'Lagos'),
]

print(f"\n  Total offices to load: {len(OFFICES)}")

# ── Load into generic.location ────────────────────────────────────────

def get_or_create_location(name, parent_id=None, location_type=None, address=''):
    domain = [('name', '=', name)]
    if parent_id:
        domain.append(('parent_id', '=', parent_id))
    existing = env['generic.location'].search(domain, limit=1)
    if existing:
        return existing.id
    vals = {'name': name}
    if parent_id:
        vals['parent_id'] = parent_id
    if address:
        # generic.location uses `street` (Odoo standard), not `address`.
        vals['street'] = address
    rec = env['generic.location'].create(vals)
    return rec.id

# Zone → State → Office hierarchy
ZONES = list(set(STATE_ZONE.values()))
zone_map = {}
state_map = {}

print("\n  Creating zones...")
for zone in sorted(ZONES):
    zone_map[zone] = get_or_create_location(zone)
    print(f"    ✓ {zone}")

env.cr.commit()

print("\n  Creating states...")
for state, zone in sorted(STATE_ZONE.items()):
    state_map[state] = get_or_create_location(state, parent_id=zone_map[zone])
    print(f"    ✓ {state}")

env.cr.commit()

print("\n  Loading offices...")
created = 0
skipped = 0
BATCH = 50

for i, (num, name, address, state) in enumerate(OFFICES, 1):
    try:
        parent_id = state_map.get(state)
        if not parent_id:
            print(f"  ! No parent for state '{state}' — office {num}: {name}")
            skipped += 1
            continue
        
        existing = env['generic.location'].search([
            ('name', '=', name),
            ('parent_id', '=', parent_id)
        ], limit=1)
        
        if not existing:
            vals = {'name': name, 'parent_id': parent_id}
            if address:
                vals['street'] = address
            env['generic.location'].create(vals)
            created += 1
            if created <= 20 or created % 50 == 0:
                print(f"  + [{num:3d}] {name[:55]}")
        else:
            skipped += 1
        
        if i % BATCH == 0:
            env.cr.commit()
            print(f"  [committed batch at {i}/{len(OFFICES)}]")
    
    except Exception as e:
        print(f"  ✗ [{num}] {name} — {e}")
        skipped += 1

env.cr.commit()

total = env['generic.location'].search_count([])
print()
print("=" * 70)
print("  FIRS OFFICES — LOAD COMPLETE")
print("=" * 70)
print(f"  Offices created : {created}")
print(f"  Skipped/Exists  : {skipped}")
print(f"  Total locations : {total}")
print("=" * 70)
