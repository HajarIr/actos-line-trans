"""
kb.py — Single source of truth for the chatbot's *scope* (what it may talk about).

The real city/product data lives in main.py (CITIES, PRODUCTS) and is passed in
to the guardrail functions at call time. This module holds everything *around*
that data so the input gate (guardrails.is_in_scope) and the output validator
(guardrails.validate_output) read their rules from ONE place:

    - the vocabulary that marks a message as "about our business"
    - the list of things the company explicitly does NOT do
    - the polite, on-brand refusal / price-deflection messages (4 languages)

Keeping this here means the form, the bot, and the validator never disagree.
"""

# ---------------------------------------------------------------------------
# 1) Vocabulary that proves a message is in our domain (per language).
#    Used by the INPUT gate. Short, ambiguous tokens (e.g. "kg", "ton") are
#    left out on purpose — weights are detected separately by extract_weight.
# ---------------------------------------------------------------------------
SERVICES_VOCAB = {
    "en": ["quote", "estimate", "price", "pricing", "shipping", "ship", "transport",
           "deliver", "delivery", "customs", "clearance", "cold chain", "refrigerated",
           "reefer", "tracking", "track", "pallet", "pallets", "express", "urgent",
           "lead time", "transit", "freight", "export", "route", "strait", "ferry",
           "invoice", "payment", "shipment"],
    "fr": ["devis", "estimation", "prix", "tarif", "expedition", "expedier", "transport",
           "livraison", "livrer", "douane", "dedouanement", "chaine du froid", "refrigere",
           "frigorifique", "suivi", "palette", "palettes", "express", "urgent", "delai",
           "transit", "fret", "export", "exportation", "itineraire", "detroit", "ferry",
           "facture", "paiement"],
    "ar": ["عرض", "سعر", "ثمن", "شحن", "نقل", "توصيل", "تسليم", "جمارك", "تخليص",
           "سلسلة التبريد", "مبرد", "تتبع", "بالته", "عاجل", "مستعجل", "مدة", "عبور",
           "تصدير", "ديوانة", "فاتورة", "شحنة"],
    "es": ["presupuesto", "precio", "envio", "enviar", "transporte", "entrega", "aduana",
           "despacho", "cadena de frio", "refrigerado", "seguimiento", "palet", "palets",
           "urgente", "plazo", "transito", "flete", "exportacion", "ruta", "estrecho",
           "factura", "pago", "envios"],
}

# Broader company / goods vocabulary (a wider net so varied phrasing still passes).
# Includes route/destination words so "which countries do you cover?", "what are
# your destinations?", "do you go to Italy?" reach the assistant instead of being
# refused by the scope gate.
DOMAIN_VOCAB = {
    "en": ["company", "actos", "service", "goods", "cargo", "fruit", "fruits", "vegetable",
           "vegetables", "produce", "truck", "driver", "border", "europe", "morocco",
           "agadir", "fresh", "destination", "destinations", "route", "routes", "country",
           "countries", "region", "regions", "cover", "where do you", "do you go", "do you serve"],
    "fr": ["entreprise", "societe", "actos", "service", "marchandise", "cargaison", "fruit",
           "fruits", "legume", "legumes", "camion", "chauffeur", "frontiere", "europe",
           "maroc", "agadir", "frais", "destination", "destinations", "pays", "ville", "villes",
           "region", "couvrez", "couvrir", "desservez", "ou expediez"],
    "ar": ["شركة", "اكتوس", "خدمة", "بضاعة", "فاكهة", "فواكه", "خضر", "خضروات", "شاحنة",
           "سائق", "حدود", "اوروبا", "المغرب", "اكادير", "طازج", "وجهة", "وجهات", "دولة",
           "دول", "بلد", "مدينة", "مدن", "منطقة", "تغطون", "هل تشحنون"],
    "es": ["empresa", "actos", "servicio", "mercancia", "carga", "fruta", "frutas", "verdura",
           "verduras", "camion", "conductor", "frontera", "europa", "marruecos", "agadir",
           "fresco", "destino", "destinos", "pais", "paises", "ciudad", "ciudades", "region",
           "cubre", "cubren", "donde envian"],
}

# ---------------------------------------------------------------------------
# 2) Strong off-topic markers. If one of these appears we refuse even when the
#    message also mentions a network city (e.g. "weather in Paris"). Kept
#    specific to avoid blocking legitimate logistics words.
# ---------------------------------------------------------------------------
OUT_OF_SCOPE_MARKERS = [
    # English
    "weather", "forecast", "capital of", "president", "football", "recipe", "cook",
    "poem", "joke", "translate", "python", "javascript", "homework", "bitcoin", "stock market",
    # French
    "meteo", "recette", "blague", "poeme", "traduis", "devoirs",
    # Spanish
    "clima", "receta", "chiste", "poema", "traducir", "tarea",
    # Arabic
    "طقس", "وصفة", "نكتة", "ترجم", "واجب",
]

# ---------------------------------------------------------------------------
# 3) Things we DON'T do. Used by the OUTPUT validator to catch the LLM
#    promising a service that doesn't exist.
# ---------------------------------------------------------------------------
UNSUPPORTED_MODES = [
    "air freight", "airfreight", "air cargo", "airplane", "aeroplane", "by air", "by plane",
    "avion", "fret aerien", "par avion", "aereo", "transporte aereo",
    "rail freight", "by train", "railway", "ferrocarril", "tren de carga",
    "sea freight", "by ship", "container ship", "transport maritime", "barco de carga",
]
UNSUPPORTED_CARGO = [
    "electronics", "furniture", "machinery", "passengers", "live animal", "live animals",
    "livestock", "cattle", "pets",
    "meubles", "passagers", "animaux vivants", "betail",
    "muebles", "pasajeros", "animales vivos", "ganado",
    "اثاث", "ركاب", "حيوانات حية", "ماشية",
]

# ---------------------------------------------------------------------------
# 3b) Well-known places we DON'T serve. Used by the FAQ geography gate so a
#     transit/customs question about an out-of-network destination is refused
#     instead of leaking the route/price table. (The quote engine independently
#     validates every city against the 31-city CITIES network; this list just
#     makes the FAQ path refuse the common confusables with high precision.)
#     Must NOT contain any served city/country (Morocco, France, Spain,
#     Portugal, Italy, Belgium, Netherlands, Germany, Austria, Ireland, UK,
#     Switzerland, or any of the 31 network cities).
# ---------------------------------------------------------------------------
FOREIGN_PLACES = [
    # North / South America
    "new york", "washington", "los angeles", "san francisco", "chicago", "boston",
    "miami", "houston", "dallas", "atlanta", "toronto", "montreal", "vancouver",
    "mexico", "mexico city", "sao paulo", "rio de janeiro", "buenos aires", "lima",
    "bogota", "santiago", "usa", "united states", "america", "canada", "brazil", "argentina",
    # Middle East
    "dubai", "abu dhabi", "doha", "riyadh", "jeddah", "kuwait", "manama", "muscat",
    "amman", "beirut", "baghdad", "tehran", "uae", "emirates", "qatar", "saudi arabia",
    "oman", "bahrain", "jordan", "lebanon", "iraq", "iran",
    # Africa (non-Morocco)
    "cairo", "alexandria", "tunis", "algiers", "dakar", "abidjan", "lagos", "accra",
    "nairobi", "addis ababa", "johannesburg", "cape town", "egypt", "tunisia", "algeria",
    "senegal", "nigeria", "ghana", "kenya", "ethiopia", "south africa",
    # Eastern Europe / Nordics / Turkey
    "moscow", "kyiv", "kiev", "warsaw", "prague", "budapest", "bucharest", "athens",
    "stockholm", "oslo", "copenhagen", "helsinki", "reykjavik", "istanbul", "ankara",
    "russia", "ukraine", "poland", "greece", "turkey", "sweden", "norway", "denmark",
    "finland", "iceland",
    # Asia / Oceania
    "tokyo", "osaka", "beijing", "shanghai", "hong kong", "shenzhen", "guangzhou",
    "seoul", "taipei", "bangkok", "singapore", "jakarta", "manila", "kuala lumpur",
    "mumbai", "delhi", "new delhi", "bangalore", "karachi", "dhaka", "sydney",
    "melbourne", "auckland", "china", "japan", "korea", "india", "pakistan",
    "bangladesh", "thailand", "vietnam", "indonesia", "malaysia", "philippines",
    "australia", "new zealand",
    # A few common Arabic forms
    "نيويورك", "دبي", "طوكيو", "القاهرة", "اسطنبول", "موسكو", "بكين",
]

# ---------------------------------------------------------------------------
# 4) On-brand canned messages (customer-service tone), per language.
# ---------------------------------------------------------------------------
REFUSAL = {
    "en": "I'm the Actos Line Trans assistant 🚚 — I can only help with our transport and "
          "logistics services: shipping quotes for fruits & vegetables, delivery times, cold "
          "chain, customs, and tracking. How can I help with your shipment?",
    "fr": "Je suis l'assistant Actos Line Trans 🚚 — je peux uniquement vous aider sur nos "
          "services de transport et de logistique : devis pour fruits et légumes, délais de "
          "livraison, chaîne du froid, douane et suivi. Comment puis-je vous aider pour votre expédition ?",
    "ar": "أنا مساعد Actos Line Trans 🚚 — يمكنني فقط مساعدتك في خدمات النقل واللوجستيك: عروض "
          "أسعار لشحن الفواكه والخضروات، آجال التسليم، سلسلة التبريد، الجمارك، والتتبع. كيف أساعدك في شحنتك؟",
    "es": "Soy el asistente de Actos Line Trans 🚚 — solo puedo ayudarte con nuestros servicios "
          "de transporte y logística: presupuestos para frutas y verduras, plazos de entrega, "
          "cadena de frío, aduana y seguimiento. ¿Cómo puedo ayudarte con tu envío?",
}

# Graceful reply when the user names a destination clearly outside our network
# (one of FOREIGN_PLACES). Lists where we DO ship and invites a valid route,
# instead of a flat refusal — keeps destination questions helpful.
OUT_OF_NETWORK = {
    "en": "That destination is outside our network — we ship by road across Morocco and Europe "
          "(for example Casablanca, Tangier, Paris, Madrid, Barcelona, Milan, Berlin). Tell me a "
          "pickup and destination within Morocco or Europe and I'll check the route and quote it.",
    "fr": "Cette destination est hors de notre réseau — nous transportons par la route au Maroc et "
          "en Europe (par exemple Casablanca, Tanger, Paris, Madrid, Barcelone, Milan, Berlin). "
          "Indiquez-moi un départ et une destination au Maroc ou en Europe et je vérifie l'itinéraire et le devis.",
    "ar": "هذه الوجهة خارج شبكتنا — ننقل برّاً داخل المغرب وأوروبا (مثلاً الدار البيضاء، طنجة، باريس، "
          "مدريد، برشلونة، ميلانو، برلين). أعطني نقطة انطلاق ووجهة داخل المغرب أو أوروبا وسأتحقق من المسار والسعر.",
    "es": "Ese destino está fuera de nuestra red — transportamos por carretera en Marruecos y Europa "
          "(por ejemplo Casablanca, Tánger, París, Madrid, Barcelona, Milán, Berlín). Dime un origen "
          "y un destino en Marruecos o Europa y comprobaré la ruta y el presupuesto.",
}

# Refusal when the user asks for a service we structurally don't provide
# (air/sea/rail freight, or non-produce cargo). Used by the rule engine BEFORE
# a quote is ever started, and by the output validator as a backstop.
UNSUPPORTED_SERVICE = {
    "en": "We only handle ROAD freight of fresh fruits & vegetables between Morocco and Europe — "
          "we don't offer air, sea or rail transport, and we can't carry non-produce goods "
          "(electronics, furniture, live animals or passengers). Can I help you ship produce by road?",
    "fr": "Nous assurons uniquement le transport ROUTIER de fruits et légumes frais entre le Maroc "
          "et l'Europe — pas de fret aérien, maritime ou ferroviaire, et nous ne transportons pas de "
          "marchandises hors produits frais (électronique, meubles, animaux vivants ou passagers). "
          "Puis-je vous aider à expédier des produits frais par la route ?",
    "ar": "نحن نقوم فقط بالنقل البري للفواكه والخضروات الطازجة بين المغرب وأوروبا — لا نوفّر الشحن "
          "الجوي أو البحري أو بالسكك الحديدية، ولا ننقل بضائع غير المنتجات الطازجة (إلكترونيات، أثاث، "
          "حيوانات حية أو ركاب). هل أساعدك في شحن منتجات طازجة برّاً؟",
    "es": "Solo realizamos transporte por CARRETERA de frutas y verduras frescas entre Marruecos y "
          "Europa — no ofrecemos transporte aéreo, marítimo ni ferroviario, y no llevamos mercancías "
          "que no sean productos frescos (electrónica, muebles, animales vivos o pasajeros). "
          "¿Te ayudo a enviar productos frescos por carretera?",
}

# Transit-time answer templates. {origin}/{dest}/{days}/{samples} are filled
# with values COMPUTED from the same distance model as the quote (single source
# of truth — no hard-coded hours anywhere). {customs} is the border-time note,
# empty for domestic Moroccan routes.
TRANSIT_CUSTOMS_NOTE = {
    "en": " plus customs clearance time at the border",
    "fr": " plus le temps de dédouanement à la frontière",
    "ar": " بالإضافة إلى وقت التخليص الجمركي عند الحدود",
    "es": " más el tiempo de despacho de aduana en la frontera",
}
TRANSIT_SPECIFIC = {
    "en": "Road transit from {origin} to {dest} is about {days}{customs}. Transit times are estimated from the route distance — the same basis as your quote.",
    "fr": "Le transport routier de {origin} à {dest} prend environ {days}{customs}. Les délais sont estimés à partir de la distance — la même base que votre devis.",
    "ar": "يستغرق النقل البري من {origin} إلى {dest} حوالي {days}{customs}. تُقدَّر المدد انطلاقاً من مسافة الطريق — نفس أساس عرض السعر.",
    "es": "El transporte por carretera de {origin} a {dest} tarda aproximadamente {days}{customs}. Los plazos se estiman a partir de la distancia — la misma base que tu presupuesto.",
}
TRANSIT_GENERIC = {
    "en": "Road transit time depends on the route distance — for example from Agadir: {samples}. Cross-border trips add customs time at the border. Times are estimated from your itinerary, the same basis as your quote.",
    "fr": "Le délai routier dépend de la distance — par exemple depuis Agadir : {samples}. Les trajets internationaux ajoutent le temps de douane à la frontière. Estimés à partir de l'itinéraire, comme votre devis.",
    "ar": "تعتمد مدة النقل البري على المسافة — مثلاً من أكادير: {samples}. تضيف الرحلات الدولية وقت الجمارك عند الحدود. تُقدَّر انطلاقاً من المسار، نفس أساس عرض السعر.",
    "es": "El plazo por carretera depende de la distancia — por ejemplo desde Agadir: {samples}. Los trayectos internacionales añaden tiempo de aduana en la frontera. Estimados a partir de la ruta, como tu presupuesto.",
}

# Substituted when the LLM tries to state a price itself (only the engine may quote).
PRICE_DEFLECTION = {
    "en": "I can't give an exact figure from memory — but I can build you a precise quote right "
          "now. Tell me the pickup city, destination, weight (kg) and product.",
    "fr": "Je ne peux pas donner un montant exact de mémoire — mais je peux vous établir un devis "
          "précis tout de suite. Indiquez-moi la ville de départ, la destination, le poids (kg) et le produit.",
    "ar": "لا أستطيع تقديم مبلغ دقيق من الذاكرة — لكن يمكنني إعداد عرض سعر دقيق الآن. أخبرني بمدينة "
          "الانطلاق والوجهة والوزن (كغ) والمنتج.",
    "es": "No puedo dar una cifra exacta de memoria — pero puedo prepararte un presupuesto preciso "
          "ahora. Dime la ciudad de origen, el destino, el peso (kg) y el producto.",
}

# Substituted when the LLM states a specific operational figure it shouldn't
# invent (deposit %, cold-chain temperature, transit duration). The exact values
# come from the deterministic FAQ / quote engine, never from the model.
FACT_DEFLECTION = {
    "en": "I'd rather give you the confirmed details for exact figures like delivery times, "
          "temperatures or deposit terms. Would you like a quote, or shall I pass you to our "
          "commercial team for the precise numbers?",
    "fr": "Pour les chiffres exacts (délais, températures, acompte), je préfère vous donner les "
          "informations confirmées. Souhaitez-vous un devis, ou que je vous mette en relation avec "
          "notre équipe commerciale pour les chiffres précis ?",
    "ar": "بالنسبة للأرقام الدقيقة (آجال التسليم، درجات الحرارة، العربون)، أفضّل أن أعطيك المعلومات "
          "المؤكدة. هل ترغب في عرض سعر، أو أن أحوّلك إلى فريقنا التجاري للحصول على الأرقام الدقيقة؟",
    "es": "Para cifras exactas (plazos, temperaturas, anticipo), prefiero darte la información "
          "confirmada. ¿Quieres un presupuesto, o te paso con nuestro equipo comercial para los "
          "números precisos?",
}
