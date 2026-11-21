import type { CustomerType, Role } from "@prisma/client";

export interface SeedUser {
  email: string;
  name: string;
  role: Role;
  phone: string;
  hourlyRatePaise?: number;
}

const technicianNames = [
  "Ravi Patil",
  "Suresh Jadhav",
  "Amit Shinde",
  "Vikas Pawar",
  "Mahesh Kale",
  "Sachin More",
  "Ganesh Chavan",
  "Prakash Gaikwad",
  "Rahul Deshmukh",
  "Santosh Bhosale",
  "Nitin Kulkarni",
  "Ajay Salunkhe",
  "Deepak Mane",
  "Sunil Thorat",
  "Yogesh Kadam",
];

/** One seeded login per role, plus the full crew of 15 technicians. Password: SEED_USER_PASSWORD. */
export const USERS: SeedUser[] = [
  { email: "admin@sunpower.test", name: "Asha Admin", role: "ADMIN", phone: "9000000001" },
  { email: "director@sunpower.test", name: "Devendra Rao", role: "DIRECTOR", phone: "9000000002" },
  { email: "sales@sunpower.test", name: "Sneha Joshi", role: "SALES", phone: "9000000003" },
  { email: "sales2@sunpower.test", name: "Kiran Mehta", role: "SALES", phone: "9000000004" },
  { email: "warehouse@sunpower.test", name: "Wasim Shaikh", role: "WAREHOUSE", phone: "9000000005" },
  { email: "support@sunpower.test", name: "Pooja Nair", role: "SUPPORT", phone: "9000000006" },
  ...technicianNames.map<SeedUser>((name, i) => ({
    email: i === 0 ? "tech@sunpower.test" : `tech${i + 1}@sunpower.test`,
    name,
    role: "TECHNICIAN",
    phone: `91000000${String(i + 10).padStart(2, "0")}`,
    // ₹150–₹290 per hour, in paise
    hourlyRatePaise: (150 + (i % 8) * 20) * 100,
  })),
];

export interface SeedCustomer {
  name: string;
  phone: string;
  type: CustomerType;
  addressLine: string;
  city: string;
  pincode: string;
  email?: string;
}

export const CUSTOMERS: SeedCustomer[] = [
  {
    name: "Anil Kulkarni",
    phone: "9822011111",
    type: "RESIDENTIAL",
    addressLine: "12 Shanti Nagar, Kothrud",
    city: "Pune",
    pincode: "411038",
  },
  {
    name: "Meera Deshpande",
    phone: "9822022222",
    type: "RESIDENTIAL",
    addressLine: "Flat 4, Sai Residency, Baner",
    city: "Pune",
    pincode: "411045",
  },
  {
    name: "Rajesh Agarwal",
    phone: "9822033333",
    type: "COMMERCIAL",
    addressLine: "Plot 18, MIDC Bhosari",
    city: "Pune",
    pincode: "411026",
    email: "rajesh@agarwalplastics.test",
  },
  {
    name: "Sunita Pawar",
    phone: "9822044444",
    type: "RESIDENTIAL",
    addressLine: "Gangapur Road, near Canada Corner",
    city: "Nashik",
    pincode: "422005",
  },
  {
    name: "Farhan Qureshi",
    phone: "9822055555",
    type: "RESIDENTIAL",
    addressLine: "22 Camp Road",
    city: "Pune",
    pincode: "411001",
  },
  {
    name: "Lakshmi Iyer",
    phone: "9822066666",
    type: "RESIDENTIAL",
    addressLine: "Row House 7, Wakad",
    city: "Pune",
    pincode: "411057",
  },
  {
    name: "Jadhav Engineering Works",
    phone: "9822077777",
    type: "COMMERCIAL",
    addressLine: "Gat 45, Chakan Industrial Area",
    city: "Pune",
    pincode: "410501",
  },
  {
    name: "Prakash Wagh",
    phone: "9822088888",
    type: "RESIDENTIAL",
    addressLine: "Satpur Colony",
    city: "Nashik",
    pincode: "422007",
  },
];

export const STOCK_LOCATIONS = [
  { code: "WH-MAIN", name: "Main warehouse, Pune", type: "WAREHOUSE" },
  { code: "VAN-1", name: "Crew van 1", type: "VEHICLE" },
  { code: "VAN-2", name: "Crew van 2", type: "VEHICLE" },
  { code: "SUPPLIER", name: "Suppliers (virtual)", type: "SUPPLIER" },
  { code: "CUSTOMER", name: "Customer sites (virtual)", type: "CUSTOMER_SITE" },
  { code: "SCRAP", name: "Scrap / returns", type: "SCRAP" },
] as const;

/** Opening stock in the main warehouse. Serialized items get one SerialUnit each. */
export const OPENING_STOCK: Record<string, number> = {
  "PNL-540-MONO": 80,
  "INV-ONG-1KW": 4,
  "INV-ONG-2KW": 4,
  "INV-ONG-3KW": 6,
  "INV-ONG-4KW": 4,
  "INV-ONG-5KW": 4,
  "CC-MPPT-24V-40A": 6,
  "CC-MPPT-48V-60A": 8,
  "BAT-12V-150AH": 24,
  "MNT-GI-PANEL": 80,
  "BOX-AJB": 20,
  "BOX-DCDB": 20,
  "BOX-ACDB": 20,
  "CBL-DC-4SQ": 1500,
  "CBL-AC-4SQ": 800,
  "CON-MC4-PAIR": 200,
  "ERT-KIT": 60,
  "ERT-WIRE-10SQ": 1000,
  "ERT-LA": 20,
};

export const APP_SETTINGS = {
  /** Minimum advance to confirm an order, in basis points of the order total (30%). */
  minAdvanceBps: 3000,
  /** Quotes are valid for this many days. */
  quoteValidityDays: 15,
  /** Labour charged to customers on out-of-warranty tickets, paise per hour (₹500). */
  ticketLabourChargePaisePerHour: 50_000,
  /** Visit charge for out-of-warranty tickets, paise (₹300). */
  ticketVisitChargePaise: 30_000,
  company: {
    name: "SunPower Solutions",
    gstin: "27ABCDE1234F1Z5",
    address: "Office 5, Solar House, Karve Road, Pune 411004",
    phone: "020-0000-0000",
  },
} as const;
