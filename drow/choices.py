"""All the options shown on the client form.

Edit these lists to change what clients can pick. The form, the server-side
validation and the Excel export all read from here, so there is one place to
change things.
"""

INSIDE_AMENITIES = [
    "Master bedroom with attached bath",
    "Kids' bedroom",
    "Guest bedroom",
    "Living room",
    "Family / upper living",
    "Dining area",
    "Modular kitchen",
    "Work area (back kitchen)",
    "Store room",
    "Prayer room",
    "Home office / study",
    "Home theatre",
    "Home gym",
    "Walk-in wardrobe",
    "Laundry / utility room",
    "Home elevator",
    "Smart home automation",
    "Central air conditioning",
]

OUTER_AMENITIES = [
    "Car porch / parking",
    "Sit-out / veranda",
    "Balcony",
    "Open terrace",
    "Garden & landscaping",
    "Central courtyard",
    "Swimming pool",
    "Kids' play area",
    "Outdoor seating / gazebo",
    "Compound wall & gate",
    "Solar panels",
    "Rainwater harvesting",
    "Well / borewell",
    "CCTV & security",
    "EV charging point",
]

FLOORS = [
    "Ground floor only",
    "G + 1",
    "G + 2",
    "G + 3 or more",
    "Not sure yet",
]

TIMELINES = [
    "Within 6 months",
    "6 - 12 months",
    "12 - 18 months",
    "18 - 24 months",
    "More than 2 years",
    "Not sure yet",
]

ARCH_STYLES = [
    "Contemporary",
    "Modern",
    "Colonial",
    "Traditional Kerala",
    "Minimalist",
    "Tropical",
    "Mediterranean",
    "Industrial",
    "Not sure - help me choose",
    "Other",
]

LAND_STATUS = [
    "I own the land",
    "I am buying the land",
    "I don't have land yet",
]

AREA_UNITS = ["Cent", "Sq.ft", "Sq.m", "Acre"]

PLOT_SHAPES = ["Rectangle / square", "Irregular", "Corner plot", "Not sure"]

PLOT_SLOPES = ["Flat", "Gentle slope", "Steep slope", "Not sure"]

CURRENCIES = ["INR", "AED", "USD", "SAR", "QAR", "OMR", "KWD", "BHD", "GBP", "EUR"]

BUDGET_FLEX = [
    "Fixed - cannot go above",
    "Can stretch a little",
    "Flexible for the right home",
]

FUNDING = ["Own funds", "Home loan", "Own funds + home loan", "Not decided"]

CONTACT_METHODS = ["WhatsApp", "Phone call", "Email"]

STATUSES = [
    "New",
    "Under review",
    "Options shared",
    "Way forward agreed",
    "Closed",
]
