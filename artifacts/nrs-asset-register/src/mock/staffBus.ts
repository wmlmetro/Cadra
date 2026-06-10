import type { BusRoute, BusSchedule, BusBooking } from "../types";

export const mockBusRoutes: BusRoute[] = [
  { id: "RT-001", code: "ABJ-LOS", name: "Abuja → Lagos",         origin: "NRS HQ, Abuja",         destination: "Ikeja LSBO, Lagos",     distanceKm: 775, estimatedDuration: "9h 30m", stops: ["Lokoja", "Ibadan"], vehicleId: "VEH-004", active: true },
  { id: "RT-002", code: "LOS-ABJ", name: "Lagos → Abuja",         origin: "Ikeja LSBO, Lagos",     destination: "NRS HQ, Abuja",         distanceKm: 775, estimatedDuration: "9h 30m", stops: ["Ibadan", "Lokoja"], vehicleId: "VEH-005", active: true },
  { id: "RT-003", code: "ABJ-KAN", name: "Abuja → Kano",          origin: "NRS HQ, Abuja",         destination: "Kano GBTO, Kano",       distanceKm: 478, estimatedDuration: "6h 00m", stops: ["Kaduna"], vehicleId: "VEH-008", active: true },
  { id: "RT-004", code: "ABJ-PHC", name: "Abuja → Port Harcourt", origin: "NRS HQ, Abuja",         destination: "Port Harcourt MSTO",    distanceKm: 590, estimatedDuration: "7h 00m", stops: ["Lokoja", "Benin City"], vehicleId: "VEH-003", active: true },
  { id: "RT-005", code: "IBA-ABJ", name: "Ibadan → Abuja",        origin: "Ibadan MSTO",           destination: "NRS HQ, Abuja",         distanceKm: 590, estimatedDuration: "6h 30m", stops: ["Lokoja"], vehicleId: "VEH-011", active: true },
  { id: "RT-006", code: "ABJ-ENK", name: "Abuja → Enugu",         origin: "NRS HQ, Abuja",         destination: "Enugu MSTO",            distanceKm: 478, estimatedDuration: "5h 45m", stops: ["Okene"], vehicleId: undefined,  active: true },
  { id: "RT-007", code: "ABJ-MDA", name: "Abuja → Maiduguri",     origin: "NRS HQ, Abuja",         destination: "Maiduguri ASMTO",       distanceKm: 820, estimatedDuration: "10h 00m", stops: ["Bauchi"], vehicleId: undefined,  active: false },
  { id: "RT-008", code: "PHC-ABJ", name: "Port Harcourt → Abuja", origin: "Port Harcourt MSTO",    destination: "NRS HQ, Abuja",         distanceKm: 590, estimatedDuration: "7h 00m", stops: ["Benin City", "Lokoja"], vehicleId: "VEH-003", active: true },
];

export const mockBusSchedules: BusSchedule[] = [
  { id: "SCH-001", routeId: "RT-001", routeCode: "ABJ-LOS", routeName: "Abuja → Lagos",         vehicleId: "VEH-004", vehicleRegNo: "ABJ-540-NK", vehicleName: "Toyota Hiace (ABJ)",    driverName: "Yakubu Hassan",  departureDate: "2026-06-10", departureTime: "06:00", estimatedArrival: "15:30", totalSeats: 18, bookedSeats: 14, checkedIn: 11, status: "In Transit",  direction: "Outbound" },
  { id: "SCH-002", routeId: "RT-004", routeCode: "ABJ-PHC", routeName: "Abuja → Port Harcourt", vehicleId: "VEH-003", vehicleRegNo: "PHC-112-XY", vehicleName: "Toyota Hiace (PHC)",    driverName: "Samuel Peters",  departureDate: "2026-06-10", departureTime: "07:30", estimatedArrival: "14:30", totalSeats: 15, bookedSeats: 15, checkedIn: 15, status: "Arrived",    direction: "Outbound" },
  { id: "SCH-003", routeId: "RT-003", routeCode: "ABJ-KAN", routeName: "Abuja → Kano",          vehicleId: "VEH-008", vehicleRegNo: "KNO-118-JK", vehicleName: "Innoson Bus G80",        driverName: "Ibrahim Musa",   departureDate: "2026-06-10", departureTime: "08:00", estimatedArrival: "14:00", totalSeats: 22, bookedSeats: 18, checkedIn: 14, status: "In Transit",  direction: "Outbound" },
  { id: "SCH-004", routeId: "RT-002", routeCode: "LOS-ABJ", routeName: "Lagos → Abuja",         vehicleId: "VEH-005", vehicleRegNo: "LOS-881-PQ", vehicleName: "Toyota Coaster Bus",    driverName: "Bello Muhammed", departureDate: "2026-06-10", departureTime: "05:30", estimatedArrival: "15:00", totalSeats: 30, bookedSeats: 26, checkedIn: 24, status: "In Transit",  direction: "Return"   },
  { id: "SCH-005", routeId: "RT-001", routeCode: "ABJ-LOS", routeName: "Abuja → Lagos",         vehicleId: "VEH-004", vehicleRegNo: "ABJ-540-NK", vehicleName: "Toyota Hiace (ABJ)",    driverName: "Yakubu Hassan",  departureDate: "2026-06-12", departureTime: "06:00", estimatedArrival: "15:30", totalSeats: 18, bookedSeats: 9,  checkedIn: 0,  status: "Scheduled",  direction: "Outbound" },
  { id: "SCH-006", routeId: "RT-003", routeCode: "ABJ-KAN", routeName: "Abuja → Kano",          vehicleId: "VEH-008", vehicleRegNo: "KNO-118-JK", vehicleName: "Innoson Bus G80",        driverName: "Ibrahim Musa",   departureDate: "2026-06-13", departureTime: "08:00", estimatedArrival: "14:00", totalSeats: 22, bookedSeats: 11, checkedIn: 0,  status: "Scheduled",  direction: "Outbound" },
  { id: "SCH-007", routeId: "RT-008", routeCode: "PHC-ABJ", routeName: "Port Harcourt → Abuja", vehicleId: "VEH-003", vehicleRegNo: "PHC-112-XY", vehicleName: "Toyota Hiace (PHC)",    driverName: "Samuel Peters",  departureDate: "2026-06-11", departureTime: "06:00", estimatedArrival: "13:00", totalSeats: 15, bookedSeats: 12, checkedIn: 0,  status: "Scheduled",  direction: "Return"   },
  { id: "SCH-008", routeId: "RT-005", routeCode: "IBA-ABJ", routeName: "Ibadan → Abuja",        vehicleId: "VEH-011", vehicleRegNo: "IBA-330-WX", vehicleName: "Toyota Hiace (Ibadan)", driverName: "Tunde Fashola",  departureDate: "2026-06-11", departureTime: "07:00", estimatedArrival: "13:30", totalSeats: 18, bookedSeats: 7,  checkedIn: 0,  status: "Boarding",   direction: "Outbound" },
  { id: "SCH-009", routeId: "RT-001", routeCode: "ABJ-LOS", routeName: "Abuja → Lagos",         vehicleId: "VEH-004", vehicleRegNo: "ABJ-540-NK", vehicleName: "Toyota Hiace (ABJ)",    driverName: "Yakubu Hassan",  departureDate: "2026-06-08", departureTime: "06:00", estimatedArrival: "15:30", totalSeats: 18, bookedSeats: 16, checkedIn: 16, status: "Arrived",    direction: "Outbound" },
  { id: "SCH-010", routeId: "RT-004", routeCode: "ABJ-PHC", routeName: "Abuja → Port Harcourt", vehicleId: "VEH-003", vehicleRegNo: "PHC-112-XY", vehicleName: "Toyota Hiace (PHC)",    driverName: "Samuel Peters",  departureDate: "2026-06-14", departureTime: "07:30", estimatedArrival: "14:30", totalSeats: 15, bookedSeats: 4,  checkedIn: 0,  status: "Scheduled",  direction: "Outbound" },
];

const depts = ["Tax Operations", "Finance", "ICT", "Compliance", "Legal", "HR", "Field Ops", "Audit"];
const zones = ["NRS Headquarters", "South West", "North West", "South South", "South East", "North East"];
const names = [
  "Adaeze Okonkwo", "Babatunde Lawal", "Chiamaka Eze", "David Osei", "Esther Musa",
  "Femi Adeyemi", "Gladys Nwachukwu", "Hassan Usman", "Ifeoma Chukwu", "James Ola",
  "Kemi Adesanya", "Ladi Garba", "Moses Ikenna", "Ngozi Obi", "Ola Peters",
  "Patience Yusuf", "Rasheed Bello", "Sarah Danladi", "Tayo Adekunle", "Uche Nwosu",
  "Victor Aliyu", "Wura Fashola", "Xmas Peter", "Yemi Adeola", "Zara Hassan",
  "Abubakar Musa", "Bukola Adewale", "Clement Nze",
];

let bookingIdCounter = 1;
const scheduleSeats: Record<string, Set<number>> = {};

function makeBooking(scheduleId: string, totalSeats: number, count: number, status: BusBooking["status"]): BusBooking[] {
  if (!scheduleSeats[scheduleId]) scheduleSeats[scheduleId] = new Set();
  const result: BusBooking[] = [];
  for (let i = 0; i < count; i++) {
    let seat = Math.floor(Math.random() * totalSeats) + 1;
    let attempts = 0;
    while (scheduleSeats[scheduleId].has(seat) && attempts < 50) { seat = Math.floor(Math.random() * totalSeats) + 1; attempts++; }
    scheduleSeats[scheduleId].add(seat);
    const nameIdx = (bookingIdCounter - 1) % names.length;
    result.push({
      id: `BKG-${String(bookingIdCounter).padStart(3, "0")}`,
      scheduleId,
      passengerName: names[nameIdx],
      passengerIR: `IR-${1000 + bookingIdCounter}`,
      department: depts[bookingIdCounter % depts.length],
      zone: zones[bookingIdCounter % zones.length],
      seatNo: seat,
      status,
      bookedAt: "2026-06-05T10:00:00Z",
      purpose: ["Official duty", "Training", "Audit exercise", "Stakeholder meeting", "Zonal visit"][bookingIdCounter % 5],
      checkinTime: status === "Checked In" || status === "Boarded" ? "06:10" : undefined,
      boardingTime: status === "Boarded" ? "06:25" : undefined,
    });
    bookingIdCounter++;
  }
  return result;
}

export const mockBusBookings: BusBooking[] = [
  ...makeBooking("SCH-001", 18, 11, "Boarded"),
  ...makeBooking("SCH-001", 18,  3, "Confirmed"),
  ...makeBooking("SCH-002", 15, 15, "Boarded"),
  ...makeBooking("SCH-003", 22, 14, "Boarded"),
  ...makeBooking("SCH-003", 22,  4, "Confirmed"),
  ...makeBooking("SCH-004", 30, 24, "Boarded"),
  ...makeBooking("SCH-004", 30,  2, "Confirmed"),
  ...makeBooking("SCH-005", 18,  9, "Confirmed"),
  ...makeBooking("SCH-006", 22, 11, "Confirmed"),
  ...makeBooking("SCH-007", 15, 12, "Confirmed"),
  ...makeBooking("SCH-008", 18,  7, "Checked In"),
];
