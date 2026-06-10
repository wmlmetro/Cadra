import type { Location } from "../types";

export const mockLocations: Location[] = [
  // ─── ZONES ──────────────────────────────────────────────────────────────────
  { id: "LOC-001", name: "NRS Headquarters", locationType: "Zone", zoneCode: "HQ",  country: "Nigeria", active: true, childrenCount: 1,  assetCount: 2800, childStates: 1,  childOffices: 16 },
  { id: "LOC-002", name: "North Central",    locationType: "Zone", zoneCode: "NC",  country: "Nigeria", active: true, childrenCount: 6,  assetCount: 1720, childStates: 6,  childOffices: 32 },
  { id: "LOC-003", name: "North East",       locationType: "Zone", zoneCode: "NE",  country: "Nigeria", active: true, childrenCount: 6,  assetCount: 1180, childStates: 6,  childOffices: 28 },
  { id: "LOC-004", name: "North West",       locationType: "Zone", zoneCode: "NW",  country: "Nigeria", active: true, childrenCount: 7,  assetCount: 2050, childStates: 7,  childOffices: 42 },
  { id: "LOC-005", name: "South East",       locationType: "Zone", zoneCode: "SE",  country: "Nigeria", active: true, childrenCount: 5,  assetCount: 1450, childStates: 5,  childOffices: 38 },
  { id: "LOC-006", name: "South South",      locationType: "Zone", zoneCode: "SS",  country: "Nigeria", active: true, childrenCount: 6,  assetCount: 1900, childStates: 6,  childOffices: 36 },
  { id: "LOC-007", name: "South West",       locationType: "Zone", zoneCode: "SW",  country: "Nigeria", active: true, childrenCount: 6,  assetCount: 2050, childStates: 6,  childOffices: 44 },

  // ─── HQ STATE ───────────────────────────────────────────────────────────────
  { id: "LOC-101", name: "FCT Office", locationType: "State", parent: "LOC-001", city: "Abuja",   state: "FCT",      country: "Nigeria", active: true, childrenCount: 16, assetCount: 2800, childOffices: 16 },

  // ─── HQ OFFICES ─────────────────────────────────────────────────────────────
  { id: "LOC-201", name: "NRS Main Building",     locationType: "Office", parent: "LOC-101", street: "Kur Mohammed Avenue",    city: "Abuja",        state: "FCT",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 1640, zoneCode: "HQ" },
  { id: "LOC-202", name: "Wuse II Annex",         locationType: "Office", parent: "LOC-101", street: "Yakubu Gowon Crescent",  city: "Wuse II",      state: "FCT",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 480,  zoneCode: "HQ" },
  { id: "LOC-203", name: "Garki Service Centre",  locationType: "Office", parent: "LOC-101", street: "Tafawa Balewa Way",      city: "Garki",        state: "FCT",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 420,  zoneCode: "HQ" },
  { id: "LOC-204", name: "Maitama Training Hub",  locationType: "Office", parent: "LOC-101", street: "Aguiyi-Ironsi Street",   city: "Maitama",      state: "FCT",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 260,  zoneCode: "HQ" },

  // ─── NORTH CENTRAL STATES ───────────────────────────────────────────────────
  { id: "LOC-102", name: "Benue State Office",    locationType: "State", parent: "LOC-002", city: "Makurdi",  state: "Benue",    country: "Nigeria", active: true,  childrenCount: 4,  assetCount: 298, childOffices: 4 },
  { id: "LOC-103", name: "Kogi State Office",     locationType: "State", parent: "LOC-002", city: "Lokoja",   state: "Kogi",     country: "Nigeria", active: true,  childrenCount: 3,  assetCount: 312, childOffices: 3 },
  { id: "LOC-104", name: "Kwara State Office",    locationType: "State", parent: "LOC-002", city: "Ilorin",   state: "Kwara",    country: "Nigeria", active: true,  childrenCount: 3,  assetCount: 276, childOffices: 3 },
  { id: "LOC-105", name: "Nasarawa State Office", locationType: "State", parent: "LOC-002", city: "Lafia",    state: "Nasarawa", country: "Nigeria", active: true,  childrenCount: 3,  assetCount: 245, childOffices: 3 },
  { id: "LOC-106", name: "Niger State Office",    locationType: "State", parent: "LOC-002", city: "Minna",    state: "Niger",    country: "Nigeria", active: true,  childrenCount: 3,  assetCount: 289, childOffices: 3 },
  { id: "LOC-107", name: "Plateau State Office",  locationType: "State", parent: "LOC-002", city: "Jos",      state: "Plateau",  country: "Nigeria", active: true,  childrenCount: 3,  assetCount: 300, childOffices: 3 },

  // ─── NC OFFICES ──────────────────────────────────────────────────────────────
  { id: "LOC-301", name: "Makurdi MSTO",    locationType: "Office", parent: "LOC-102", street: "Joseph S Tarka Way",  city: "Makurdi",   state: "Benue",    country: "Nigeria", active: true,  childrenCount: 0, assetCount: 162, zoneCode: "NC" },
  { id: "LOC-302", name: "Otukpo ASMTO",   locationType: "Office", parent: "LOC-102", street: "Station Road",        city: "Otukpo",    state: "Benue",    country: "Nigeria", active: true,  childrenCount: 0, assetCount: 88,  zoneCode: "NC" },
  { id: "LOC-303", name: "Lokoja MSTO",    locationType: "Office", parent: "LOC-103", street: "Lugard Road",         city: "Lokoja",    state: "Kogi",     country: "Nigeria", active: true,  childrenCount: 0, assetCount: 174, zoneCode: "NC" },
  { id: "LOC-304", name: "Okene ASMTO",    locationType: "Office", parent: "LOC-103", street: "Auchi Road",          city: "Okene",     state: "Kogi",     country: "Nigeria", active: true,  childrenCount: 0, assetCount: 92,  zoneCode: "NC" },
  { id: "LOC-305", name: "Ilorin LSBO",    locationType: "Office", parent: "LOC-104", street: "Plot 83 Ahmadu Bello", city: "Ilorin",   state: "Kwara",    country: "Nigeria", active: true,  childrenCount: 0, assetCount: 155, zoneCode: "NC" },

  // ─── NORTH EAST STATES ───────────────────────────────────────────────────────
  { id: "LOC-108", name: "Bauchi State Office",    locationType: "State", parent: "LOC-003", city: "Bauchi",     state: "Bauchi",   country: "Nigeria", active: true,  childrenCount: 3, assetCount: 264, childOffices: 3 },
  { id: "LOC-109", name: "Borno State Office",     locationType: "State", parent: "LOC-003", city: "Maiduguri",  state: "Borno",    country: "Nigeria", active: true,  childrenCount: 3, assetCount: 198, childOffices: 3 },
  { id: "LOC-110", name: "Gombe State Office",     locationType: "State", parent: "LOC-003", city: "Gombe",      state: "Gombe",    country: "Nigeria", active: true,  childrenCount: 2, assetCount: 188, childOffices: 2 },
  { id: "LOC-111", name: "Adamawa State Office",   locationType: "State", parent: "LOC-003", city: "Yola",       state: "Adamawa",  country: "Nigeria", active: true,  childrenCount: 2, assetCount: 196, childOffices: 2 },

  // ─── NE OFFICES ──────────────────────────────────────────────────────────────
  { id: "LOC-306", name: "Bauchi MSTO",        locationType: "Office", parent: "LOC-108", street: "Murtala Mohammed Way", city: "Bauchi",    state: "Bauchi",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 158, zoneCode: "NE" },
  { id: "LOC-307", name: "Azare ASMTO",        locationType: "Office", parent: "LOC-108", street: "Azare-Potiskum Road",  city: "Azare",     state: "Bauchi",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 82,  zoneCode: "NE" },
  { id: "LOC-308", name: "Maiduguri ASMTO",    locationType: "Office", parent: "LOC-109", street: "Kashim Ibrahim Way",   city: "Maiduguri", state: "Borno",   country: "Nigeria", active: false, childrenCount: 0, assetCount: 120, zoneCode: "NE" },
  { id: "LOC-309", name: "Biu ASMTO",          locationType: "Office", parent: "LOC-109", street: "Hospital Road",        city: "Biu",       state: "Borno",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 64,  zoneCode: "NE" },

  // ─── NORTH WEST STATES ───────────────────────────────────────────────────────
  { id: "LOC-112", name: "Kano State Office",    locationType: "State", parent: "LOC-004", city: "Kano",           state: "Kano",    country: "Nigeria", active: true, childrenCount: 5, assetCount: 448, childOffices: 5 },
  { id: "LOC-113", name: "Kaduna State Office",  locationType: "State", parent: "LOC-004", city: "Kaduna",         state: "Kaduna",  country: "Nigeria", active: true, childrenCount: 4, assetCount: 380, childOffices: 4 },
  { id: "LOC-114", name: "Sokoto State Office",  locationType: "State", parent: "LOC-004", city: "Sokoto",         state: "Sokoto",  country: "Nigeria", active: true, childrenCount: 3, assetCount: 295, childOffices: 3 },
  { id: "LOC-115", name: "Katsina State Office", locationType: "State", parent: "LOC-004", city: "Katsina",        state: "Katsina", country: "Nigeria", active: true, childrenCount: 3, assetCount: 270, childOffices: 3 },

  // ─── NW OFFICES ──────────────────────────────────────────────────────────────
  { id: "LOC-310", name: "Kano GBTO",           locationType: "Office", parent: "LOC-112", street: "Murtala Mohammed Way", city: "Kano",   state: "Kano",    country: "Nigeria", active: true,  childrenCount: 0, assetCount: 248, zoneCode: "NW" },
  { id: "LOC-311", name: "Kano Central MSTO",   locationType: "Office", parent: "LOC-112", street: "Bello Road",          city: "Kano",   state: "Kano",    country: "Nigeria", active: true,  childrenCount: 0, assetCount: 132, zoneCode: "NW" },
  { id: "LOC-312", name: "Kaduna LSBO",         locationType: "Office", parent: "LOC-113", street: "Ahmadu Bello Way",    city: "Kaduna", state: "Kaduna",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 210, zoneCode: "NW" },
  { id: "LOC-313", name: "Zaria MSTO",          locationType: "Office", parent: "LOC-113", street: "Kofar-Ruwa Road",     city: "Zaria",  state: "Kaduna",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 118, zoneCode: "NW" },
  { id: "LOC-314", name: "Sokoto ASMTO",        locationType: "Office", parent: "LOC-114", street: "Sahabi Road",         city: "Sokoto", state: "Sokoto",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 162, zoneCode: "NW" },

  // ─── SOUTH EAST STATES ───────────────────────────────────────────────────────
  { id: "LOC-116", name: "Enugu State Office",  locationType: "State", parent: "LOC-005", city: "Enugu",    state: "Enugu",    country: "Nigeria", active: true, childrenCount: 4, assetCount: 342, childOffices: 4 },
  { id: "LOC-117", name: "Imo State Office",    locationType: "State", parent: "LOC-005", city: "Owerri",   state: "Imo",      country: "Nigeria", active: true, childrenCount: 3, assetCount: 285, childOffices: 3 },
  { id: "LOC-118", name: "Anambra State Office",locationType: "State", parent: "LOC-005", city: "Awka",     state: "Anambra",  country: "Nigeria", active: true, childrenCount: 3, assetCount: 316, childOffices: 3 },
  { id: "LOC-119", name: "Abia State Office",   locationType: "State", parent: "LOC-005", city: "Umuahia", state: "Abia",     country: "Nigeria", active: true, childrenCount: 2, assetCount: 248, childOffices: 2 },

  // ─── SE OFFICES ──────────────────────────────────────────────────────────────
  { id: "LOC-315", name: "Enugu MSTO",      locationType: "Office", parent: "LOC-116", street: "Okpara Avenue",       city: "Enugu",   state: "Enugu",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 194, zoneCode: "SE" },
  { id: "LOC-316", name: "Onitsha ASMTO",   locationType: "Office", parent: "LOC-118", street: "New Market Road",     city: "Onitsha", state: "Anambra", country: "Nigeria", active: true,  childrenCount: 0, assetCount: 156, zoneCode: "SE" },
  { id: "LOC-317", name: "Owerri LSBO",     locationType: "Office", parent: "LOC-117", street: "Assumpta Avenue",     city: "Owerri",  state: "Imo",      country: "Nigeria", active: true,  childrenCount: 0, assetCount: 162, zoneCode: "SE" },

  // ─── SOUTH SOUTH STATES ──────────────────────────────────────────────────────
  { id: "LOC-120", name: "Rivers State Office", locationType: "State", parent: "LOC-006", city: "Port Harcourt", state: "Rivers",  country: "Nigeria", active: true, childrenCount: 4, assetCount: 448, childOffices: 4 },
  { id: "LOC-121", name: "Delta State Office",  locationType: "State", parent: "LOC-006", city: "Asaba",         state: "Delta",   country: "Nigeria", active: true, childrenCount: 3, assetCount: 318, childOffices: 3 },
  { id: "LOC-122", name: "Edo State Office",    locationType: "State", parent: "LOC-006", city: "Benin City",    state: "Edo",     country: "Nigeria", active: true, childrenCount: 3, assetCount: 296, childOffices: 3 },
  { id: "LOC-123", name: "Cross River Office",  locationType: "State", parent: "LOC-006", city: "Calabar",       state: "Cross River", country: "Nigeria", active: true, childrenCount: 3, assetCount: 310, childOffices: 3 },

  // ─── SS OFFICES ──────────────────────────────────────────────────────────────
  { id: "LOC-318", name: "Port Harcourt MSTO", locationType: "Office", parent: "LOC-120", street: "Aba Road",            city: "Port Harcourt", state: "Rivers",      country: "Nigeria", active: true,  childrenCount: 0, assetCount: 248, zoneCode: "SS" },
  { id: "LOC-319", name: "GRA Office PH",      locationType: "Office", parent: "LOC-120", street: "Peter Odili Road",    city: "Port Harcourt", state: "Rivers",      country: "Nigeria", active: true,  childrenCount: 0, assetCount: 138, zoneCode: "SS" },
  { id: "LOC-320", name: "Asaba MSTO",         locationType: "Office", parent: "LOC-121", street: "Nnebisi Road",        city: "Asaba",         state: "Delta",       country: "Nigeria", active: true,  childrenCount: 0, assetCount: 172, zoneCode: "SS" },
  { id: "LOC-321", name: "Warri LSBO",         locationType: "Office", parent: "LOC-121", street: "Effurun Road",        city: "Warri",         state: "Delta",       country: "Nigeria", active: true,  childrenCount: 0, assetCount: 112, zoneCode: "SS" },
  { id: "LOC-322", name: "Benin LSBO",         locationType: "Office", parent: "LOC-122", street: "Akpakpava Road",      city: "Benin City",    state: "Edo",         country: "Nigeria", active: true,  childrenCount: 0, assetCount: 168, zoneCode: "SS" },
  { id: "LOC-323", name: "Calabar MSTO",       locationType: "Office", parent: "LOC-123", street: "Mary Slessor Avenue", city: "Calabar",       state: "Cross River", country: "Nigeria", active: true,  childrenCount: 0, assetCount: 178, zoneCode: "SS" },

  // ─── SOUTH WEST STATES ───────────────────────────────────────────────────────
  { id: "LOC-124", name: "Lagos State Office",    locationType: "State", parent: "LOC-007", city: "Lagos",   state: "Lagos",  country: "Nigeria", active: true, childrenCount: 6, assetCount: 680, childOffices: 6 },
  { id: "LOC-125", name: "Oyo State Office",      locationType: "State", parent: "LOC-007", city: "Ibadan",  state: "Oyo",   country: "Nigeria", active: true, childrenCount: 4, assetCount: 378, childOffices: 4 },
  { id: "LOC-126", name: "Ogun State Office",     locationType: "State", parent: "LOC-007", city: "Abeokuta",state: "Ogun",  country: "Nigeria", active: true, childrenCount: 3, assetCount: 295, childOffices: 3 },
  { id: "LOC-127", name: "Osun State Office",     locationType: "State", parent: "LOC-007", city: "Osogbo",  state: "Osun",  country: "Nigeria", active: true, childrenCount: 3, assetCount: 268, childOffices: 3 },

  // ─── SW OFFICES ──────────────────────────────────────────────────────────────
  { id: "LOC-324", name: "Ikeja LSBO",          locationType: "Office", parent: "LOC-124", street: "Obafemi Awolowo Way",  city: "Ikeja",    state: "Lagos",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 198, zoneCode: "SW" },
  { id: "LOC-325", name: "Lagos Island GBTO",   locationType: "Office", parent: "LOC-124", street: "Marina Road",          city: "Lagos",    state: "Lagos",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 176, zoneCode: "SW" },
  { id: "LOC-326", name: "Apapa MSTO",          locationType: "Office", parent: "LOC-124", street: "Wharf Road",           city: "Apapa",    state: "Lagos",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 148, zoneCode: "SW" },
  { id: "LOC-327", name: "Lekki Service Centre",locationType: "Office", parent: "LOC-124", street: "Lekki-Epe Expressway", city: "Lekki",    state: "Lagos",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 98,  zoneCode: "SW" },
  { id: "LOC-328", name: "Ibadan MSTO",         locationType: "Office", parent: "LOC-125", street: "Ring Road",            city: "Ibadan",   state: "Oyo",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 210, zoneCode: "SW" },
  { id: "LOC-329", name: "Ogbomosho ASMTO",     locationType: "Office", parent: "LOC-125", street: "Ilorin Road",          city: "Ogbomosho",state: "Oyo",   country: "Nigeria", active: true,  childrenCount: 0, assetCount: 98,  zoneCode: "SW" },
  { id: "LOC-330", name: "Abeokuta LSBO",       locationType: "Office", parent: "LOC-126", street: "Lalubu Road",          city: "Abeokuta", state: "Ogun",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 168, zoneCode: "SW" },
  { id: "LOC-331", name: "Sango-Ota ASMTO",     locationType: "Office", parent: "LOC-126", street: "Lagos Road",           city: "Sango-Ota",state: "Ogun",  country: "Nigeria", active: false, childrenCount: 0, assetCount: 82,  zoneCode: "SW" },
  { id: "LOC-332", name: "Osogbo MSTO",         locationType: "Office", parent: "LOC-127", street: "Oluode Road",          city: "Osogbo",   state: "Osun",  country: "Nigeria", active: true,  childrenCount: 0, assetCount: 148, zoneCode: "SW" },
];
