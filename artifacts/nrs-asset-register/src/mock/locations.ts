import type { Location } from '../types';

export const mockLocations: Location[] = [
  {
    id: "LOC-001",
    name: "NRS Headquarters",
    locationType: "Zone",
    zoneCode: "HQ",
    country: "Nigeria",
    active: true,
    childrenCount: 16
  },
  {
    id: "LOC-002",
    name: "North Central",
    locationType: "Zone",
    zoneCode: "NC",
    country: "Nigeria",
    active: true,
    childrenCount: 6
  },
  {
    id: "LOC-003",
    name: "North East",
    locationType: "Zone",
    zoneCode: "NE",
    country: "Nigeria",
    active: true,
    childrenCount: 6
  },
  {
    id: "LOC-004",
    name: "North West",
    locationType: "Zone",
    zoneCode: "NW",
    country: "Nigeria",
    active: true,
    childrenCount: 7
  },
  {
    id: "LOC-005",
    name: "South East",
    locationType: "Zone",
    zoneCode: "SE",
    country: "Nigeria",
    active: true,
    childrenCount: 5
  },
  {
    id: "LOC-006",
    name: "South South",
    locationType: "Zone",
    zoneCode: "SS",
    country: "Nigeria",
    active: true,
    childrenCount: 6
  },
  {
    id: "LOC-007",
    name: "South West",
    locationType: "Zone",
    zoneCode: "SW",
    country: "Nigeria",
    active: true,
    childrenCount: 6
  },
  {
    id: "LOC-101",
    name: "FCT Office",
    locationType: "State",
    parent: "LOC-001",
    city: "Abuja",
    state: "FCT",
    country: "Nigeria",
    active: true,
    childrenCount: 16
  },
  {
    id: "LOC-201",
    name: "10th Floor",
    locationType: "Floor",
    zoneCode: "F10",
    parent: "LOC-101",
    street: "Kur Mohammed Avenue",
    city: "Central Business District",
    state: "FCT",
    country: "Nigeria",
    active: true,
    childrenCount: 0
  },
  {
    id: "LOC-102",
    name: "Lagos State Office",
    locationType: "State",
    parent: "LOC-007",
    city: "Lagos",
    state: "Lagos",
    country: "Nigeria",
    active: true,
    childrenCount: 4
  },
  {
    id: "LOC-202",
    name: "Ikeja LSBO",
    locationType: "Office",
    parent: "LOC-102",
    street: "Obafemi Awolowo Way",
    city: "Ikeja",
    state: "Lagos",
    country: "Nigeria",
    active: true,
    childrenCount: 0
  },
  {
    id: "LOC-103",
    name: "Kano State Office",
    locationType: "State",
    parent: "LOC-004",
    city: "Kano",
    state: "Kano",
    country: "Nigeria",
    active: true,
    childrenCount: 3
  },
  {
    id: "LOC-203",
    name: "Kano GBTO",
    locationType: "Office",
    parent: "LOC-103",
    street: "Murtala Mohammed Way",
    city: "Kano",
    state: "Kano",
    country: "Nigeria",
    active: true,
    childrenCount: 0
  },
  {
    id: "LOC-104",
    name: "Rivers State Office",
    locationType: "State",
    parent: "LOC-006",
    city: "Port Harcourt",
    state: "Rivers",
    country: "Nigeria",
    active: true,
    childrenCount: 2
  },
  {
    id: "LOC-204",
    name: "Port Harcourt MSTO",
    locationType: "Office",
    parent: "LOC-104",
    street: "Aba Road",
    city: "Port Harcourt",
    state: "Rivers",
    country: "Nigeria",
    active: true,
    childrenCount: 0
  }
];
