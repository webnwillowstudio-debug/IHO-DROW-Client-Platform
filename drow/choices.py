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


# What the client sees on the status page for each team status
CLIENT_STATUS = {
    "New": ("Received", "We have received your DROW. Our team will review it soon."),
    "Under review": ("Under review", "Our technical team is studying your Dream and Resources."),
    "Options shared": ("Options shared", "We have shared design options with you."),
    "Way forward agreed": ("Way forward agreed", "We have agreed the way forward together."),
    "Closed": ("Closed", "This enquiry is closed. Thank you for choosing Intelligent House Owner."),
}

# Ready-made messages the team can drop into "Message to client" and then edit
MESSAGE_TEMPLATES = [
    ("Resources gap - confirm before site visit", """Dear Sir,

As per our standard process, the next step is to schedule a site visit by our architect.

However, based on our preliminary analysis of your Dream and the Resources you've shared, we noticed that your proposed home (approximately 4,500-5,000 sq. ft.) may not be achievable within your current resources.

Before proceeding with the site visit, we would like to confirm one important point.

You may choose either to:

• Align your dream with your current resources, or
• Enhance your resources to achieve your dream.

If you're willing to proceed with either of these, simply reply "YES".

Our architect will visit your site and present the best possible design options based on your Dream and Resources. You can then choose the option that best suits your priorities. We will also prepare a rough conceptual plan for your selected option.

This entire process, including the site visit, option presentation, and rough conceptual plan, is complimentary.

If neither is an option, we completely understand. Thank you for considering Intelligent House Owner. We sincerely appreciate the opportunity and wish you all the very best."""),
]
