import type { Asset } from '../types';

// `condition` here is the `nrs.asset.condition` KEY — `good`, not "Good" —
// because that is what a live asset carries and what the offline path filters
// on. These rows spelled the old display words, which meant the mock register
// and the live one disagreed about the same field: the mock could never hold a
// `new` asset, and the mock Condition filter compared display strings while the
// live one sent model keys to the API.
export const mockAssets: Asset[] = [
  {
    id: "AST-1001",
    name: "Dell OptiPlex 7090",
    assetTag: "NRS-IT-D-001",
    legacyCode: "FIRS-COMP-0992",
    category: "IT Equipment",
    subcategory: "Desktop Computer",
    assetType: "Hardware",
    manufacturer: "Dell",
    model: "OptiPlex 7090",
    serial: "DL-908123-X",
    fmDomain: "it",
    condition: "good",
    custodianName: "Amina Yusuf",
    custodianIR: "IR-9021",
    department: "Tax Operations",
    location: {
      zone: "NRS Headquarters",
      state: "FCT",
      office: "10th Floor",
      path: "NRS Headquarters / FCT / 10th Floor"
    },
    status: "Cleared",
    reviewFlags: []
  },
  {
    id: "AST-1002",
    name: "Toyota Land Cruiser SUV",
    assetTag: "NRS-FL-T-005",
    legacyCode: "FIRS-VEH-011",
    category: "Fleet / Vehicles",
    subcategory: "SUV",
    assetType: "Vehicle",
    manufacturer: "Toyota",
    model: "Land Cruiser",
    serial: "VIN-JD89234798",
    registrationNo: "ABJ-234-GH",
    engineNo: "ENG-88234-ZZ",
    condition: "fair",
    custodianName: "Chukwudi Okafor",
    custodianIR: "IR-4412",
    department: "Executive Management",
    location: {
      zone: "NRS Headquarters",
      state: "FCT",
      office: "Basement Parking",
      path: "NRS Headquarters / FCT / Basement Parking"
    },
    status: "Review — VIN not verifiable",
    reviewFlags: ["VIN format mismatch"],
    custodianScore: 85
  },
  {
    id: "AST-1003",
    name: "Executive Mahogany Desk",
    assetTag: "NRS-FN-D-044",
    legacyCode: "FIRS-FURN-102",
    category: "Furniture & Fittings",
    subcategory: "Desk",
    assetType: "Furniture",
    manufacturer: "Julius Berger Furniture",
    model: "Exec-MD-01",
    serial: "N/A",
    condition: "good",
    custodianName: "Oluwaseun Adebayo",
    custodianIR: "IR-8821",
    department: "Human Resources",
    location: {
      zone: "South West",
      state: "Lagos State Office",
      office: "Ikeja LSBO",
      path: "South West / Lagos State Office / Ikeja LSBO"
    },
    status: "Cleared",
    reviewFlags: []
  },
  {
    id: "AST-1004",
    name: "HP LaserJet Pro M404n",
    assetTag: "NRS-IT-P-022",
    legacyCode: "FIRS-PRN-055",
    category: "IT Equipment",
    subcategory: "Printer",
    assetType: "Hardware",
    manufacturer: "HP",
    model: "LaserJet Pro M404n",
    serial: "VNF-89234",
    fmDomain: "it",
    condition: "decommissioned",
    department: "Audit",
    location: {
      zone: "South West",
      state: "Lagos State Office",
      office: "Ikeja LSBO",
      path: "South West / Lagos State Office / Ikeja LSBO"
    },
    status: "Review — data quality",
    reviewFlags: ["Missing custodian", "Incorrect status mapping"]
  },
  {
    id: "AST-1005",
    name: "Innoson IVM G40 Pickup",
    assetTag: "NRS-FL-P-012",
    legacyCode: "FIRS-VEH-088",
    category: "Fleet / Vehicles",
    subcategory: "Pickup Truck",
    assetType: "Vehicle",
    manufacturer: "Innoson",
    model: "IVM G40",
    serial: "VIN-INV882347",
    registrationNo: "KNO-991-AB",
    engineNo: "ENG-INV-001",
    condition: "good",
    custodianName: "Ibrahim Musa",
    custodianIR: "IR-2201",
    department: "Field Operations",
    location: {
      zone: "North West",
      state: "Kano State Office",
      office: "Kano GBTO",
      path: "North West / Kano State Office / Kano GBTO"
    },
    status: "Cleared",
    reviewFlags: [],
    custodianScore: 92
  },
  {
    id: "AST-1006",
    name: "Lenovo ThinkPad T14",
    assetTag: "NRS-IT-L-105",
    legacyCode: "FIRS-COMP-2041",
    category: "IT Equipment",
    subcategory: "Laptop",
    assetType: "Hardware",
    manufacturer: "Lenovo",
    model: "ThinkPad T14",
    serial: "PF-29384",
    fmDomain: "it",
    condition: "good",
    custodianName: "Fatima Bello",
    custodianIR: "IR-5510",
    department: "Tax Audit",
    location: {
      zone: "North West",
      state: "Kano State Office",
      office: "Kano GBTO",
      path: "North West / Kano State Office / Kano GBTO"
    },
    status: "Review — possible duplicate",
    reviewFlags: ["Duplicate serial number PF-29384 found"]
  },
  {
    id: "AST-1007",
    name: "Conference Table (12-Seater)",
    assetTag: "NRS-FN-C-002",
    legacyCode: "FIRS-FURN-882",
    category: "Furniture & Fittings",
    subcategory: "Table",
    assetType: "Furniture",
    manufacturer: "Lifemate",
    model: "CONF-12",
    serial: "N/A",
    condition: "good",
    department: "Administration",
    location: {
      zone: "South South",
      state: "Rivers State Office",
      office: "Port Harcourt MSTO",
      path: "South South / Rivers State Office / Port Harcourt MSTO"
    },
    status: "Cleared",
    reviewFlags: []
  },
  {
    id: "AST-1008",
    name: "Toyota Hiace Staff Bus",
    assetTag: "NRS-FL-B-004",
    legacyCode: "FIRS-VEH-042",
    category: "Fleet / Vehicles",
    subcategory: "Bus",
    assetType: "Vehicle",
    manufacturer: "Toyota",
    model: "Hiace",
    serial: "VIN-TH882347",
    registrationNo: "PHC-112-XY",
    engineNo: "ENG-TH-882",
    condition: "fair",
    custodianName: "Samuel Peters",
    custodianIR: "IR-1102",
    department: "Transport",
    location: {
      zone: "South South",
      state: "Rivers State Office",
      office: "Port Harcourt MSTO",
      path: "South South / Rivers State Office / Port Harcourt MSTO"
    },
    status: "Review — allottee not in nominal roll",
    reviewFlags: ["Custodian IR-1102 not found in HR system"],
    custodianScore: 60
  }
];

// Replicate to get ~40 items for realistic volume
const moreAssets: typeof mockAssets = [];
for (let i = 0; i < 4; i++) {
  mockAssets.forEach(a => {
    moreAssets.push({
      ...a,
      id: `${a.id}-${i}`,
      assetTag: `${a.assetTag}-${i}`,
      serial: `${a.serial}-${i}`
    });
  });
}

export const allMockAssets = [...mockAssets, ...moreAssets];