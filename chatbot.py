"""
Multilingual NLU chatbot for Actos Line Trans.

Languages supported: English (en), French (fr), Arabic (ar), Spanish (es)

Pipeline (kept simple on purpose, runs offline, no paid API):

    user_text
        |
        v
    [normalize] -- strip diacritics, lowercase, collapse spaces
        |
        v
    [detect_language] -- simple keyword/character-set vote
        |
        v
    [extract_entities] -- city, weight, product (per-language synonyms)
        |
        v
    [classify_intent]  -- greeting / quote / faq / product / track / help / lang / thanks / fallback
        |
        v
    [dialog manager]   -- holds session state, asks for the next missing slot
        |
        v
    response in the user's language (+ optional structured payload)

This module is imported by main.py which exposes /api/chatbot.
"""

import re
import unicodedata
import uuid
from typing import Dict, Any, List, Optional, Tuple

import kb


# -----------------------------------------------------------------------------
# Knowledge base / strings, keyed by language
# -----------------------------------------------------------------------------

LANG_NAMES = {"en": "English", "fr": "Français", "ar": "العربية", "es": "Español"}

# Static strings the bot uses to talk to the user.
STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "greet": "👋 Hello! I'm the Actos Line Trans assistant. I can quote shipments of fruits and vegetables, answer questions about cold chain and customs, or help you track an order. What can I do for you?",
        "ask_pickup": "From which city are you shipping?",
        "ask_dest": "What is the destination city?",
        "ask_weight": "How many kilograms?",
        "ask_product": "What are you shipping? (e.g. tomatoes, strawberries, citrus, avocado, green beans, mixed)",
        "ask_cold": "Do you need refrigerated transport (cold chain)?",
        "ask_name": "What is your name?",
        "ask_contact": "What is your contact phone number?",
        "computing": "One moment, computing your quote...",
        "quote_ready": "Here is your estimated quote:",
        "saved": "Your quote has been saved (#{id}) and our commercial team has been notified.",
        "thanks": "You're welcome! Anything else?",
        "fallback": "I'm the Actos Line Trans assistant 🚚 — I can only help with our company and transport services (shipping quotes, delivery times, cold chain, customs, tracking…). How can I help with your shipment? For example: \"quote tomatoes Agadir to Madrid 5000 kg\" or \"do you ship to Paris?\"",
        "help": "I can: 💰 build a quote • 📦 give product info • 🚚 track an order • 🌐 switch language. Type 'quote' to start a quote.",
        "lang_switched": "Language switched to English.",
        "track_intro": "Tracking is simulated for now. Open the Tracking page to see your shipment on the map.",
        "missing": "I need a bit more information.",
        "yes_words": "yes,yep,yeah,sure,ok,okay,please",
        "no_words":  "no,nope,nah",
        "city_unknown": "I couldn't find that city in our network. Available examples: Agadir, Casablanca, Madrid, Paris, Barcelona, Marseille...",
        "weight_unknown": "Please give a weight in kilograms (a positive number).",
        "product_unknown": "I don't know that product yet. Try: tomatoes, strawberries, citrus, avocado, green beans, melons, potatoes, mixed.",
        "cold_forced": "❄️ {product} requires cold chain — I've enabled refrigerated transport for you.",
        "ask_customs": "Would you like us to handle customs clearance & transit, or transport only? (yes = we handle customs)",
        "ask_urgent": "Is this shipment urgent / do you need express delivery?",
        "cancelled": "No problem, I've cancelled this quote. We can start over whenever you like. 👍",
    },
    "fr": {
        "greet": "👋 Bonjour ! Je suis l'assistant Actos Line Trans. Je peux estimer un devis pour vos fruits et légumes, répondre aux questions sur la chaîne du froid et la douane, ou aider à suivre une commande. Que puis-je faire pour vous ?",
        "ask_pickup": "Depuis quelle ville expédiez-vous ?",
        "ask_dest": "Quelle est la ville de destination ?",
        "ask_weight": "Combien de kilogrammes ?",
        "ask_product": "Que transportez-vous ? (ex. tomates, fraises, agrumes, avocat, haricots verts, mélangé)",
        "ask_cold": "Avez-vous besoin d'un transport réfrigéré (chaîne du froid) ?",
        "ask_name": "Quel est votre nom ?",
        "ask_contact": "Quel est votre numéro de téléphone ?",
        "computing": "Un instant, je calcule votre devis...",
        "quote_ready": "Voici votre devis estimé :",
        "saved": "Votre devis a été enregistré (#{id}) et notre équipe commerciale a été notifiée.",
        "thanks": "Avec plaisir ! Autre chose ?",
        "fallback": "Je suis l'assistant Actos Line Trans 🚚 — je peux uniquement vous aider sur notre entreprise et nos services de transport (devis, délais, chaîne du froid, douane, suivi…). Comment puis-je vous aider pour votre expédition ? Par exemple : « devis tomates Agadir vers Madrid 5000 kg » ou « expédiez-vous vers Paris ? »",
        "help": "Je peux : 💰 faire un devis • 📦 donner des infos produit • 🚚 suivre une commande • 🌐 changer de langue. Tapez 'devis' pour commencer.",
        "lang_switched": "Langue changée en français.",
        "track_intro": "Le suivi est simulé pour l'instant. Ouvrez la page Suivi pour voir votre expédition sur la carte.",
        "missing": "Il me manque une information.",
        "yes_words": "oui,ouais,d'accord,ok,bien sûr,svp,s'il vous plaît",
        "no_words":  "non,pas,jamais",
        "city_unknown": "Je ne trouve pas cette ville. Exemples disponibles : Agadir, Casablanca, Madrid, Paris, Barcelone, Marseille...",
        "weight_unknown": "Veuillez donner un poids en kilogrammes (un nombre positif).",
        "product_unknown": "Je ne connais pas ce produit. Essayez : tomates, fraises, agrumes, avocat, haricots verts, melons, pommes de terre, mélangé.",
        "cold_forced": "❄️ {product} nécessite la chaîne du froid — j'ai activé le transport réfrigéré.",
        "ask_customs": "Souhaitez-vous que nous gérions le dédouanement et le transit, ou uniquement le transport ? (oui = nous gérons la douane)",
        "ask_urgent": "Cette expédition est-elle urgente / avez-vous besoin d'une livraison express ?",
        "cancelled": "Pas de souci, j'ai annulé ce devis. Nous pouvons recommencer quand vous voulez. 👍",
    },
    "ar": {
        "greet": "👋 أهلاً! أنا المساعد الذكي لـ Actos Line Trans. أستطيع حساب عرض سعر لشحنات الفواكه والخضروات، والإجابة عن أسئلة سلسلة التبريد والجمارك، وتتبّع طلبيّتك. كيف أساعدك؟",
        "ask_pickup": "من أي مدينة سيتم الشحن؟",
        "ask_dest": "ما هي مدينة الوجهة؟",
        "ask_weight": "كم كيلوغرام؟",
        "ask_product": "ما المنتج الذي تشحنه؟ (طماطم، فراولة، حمضيات، أفوكادو، فاصوليا خضراء، متنوع...)",
        "ask_cold": "هل تحتاج إلى نقل مبرّد (سلسلة التبريد)؟",
        "ask_name": "ما هو اسمك؟",
        "ask_contact": "ما هو رقم هاتفك؟",
        "computing": "لحظة من فضلك، يتم حساب العرض...",
        "quote_ready": "هذا هو العرض التقديري:",
        "saved": "تم حفظ العرض (#{id}) وإشعار الفريق التجاري.",
        "thanks": "العفو! هل تحتاج شيئاً آخر؟",
        "fallback": "أنا مساعد Actos Line Trans 🚚 — يمكنني فقط مساعدتك في ما يخصّ شركتنا وخدمات النقل (عروض الأسعار، آجال التسليم، سلسلة التبريد، الجمارك، التتبّع…). كيف أساعدك في شحنتك؟ مثلاً: «عرض طماطم من أكادير إلى مدريد 5000 كغ» أو «هل تشحنون إلى باريس؟»",
        "help": "أستطيع: 💰 حساب عرض سعر • 📦 معلومات منتج • 🚚 تتبّع طلبية • 🌐 تغيير اللغة. اكتب «عرض» للبدء.",
        "lang_switched": "تم تغيير اللغة إلى العربية.",
        "track_intro": "التتبّع محاكى حالياً. افتح صفحة التتبّع لرؤية الشحنة على الخريطة.",
        "missing": "أحتاج إلى مزيد من المعلومات.",
        "yes_words": "نعم,أيوا,موافق,بالتأكيد,حسناً,من فضلك",
        "no_words":  "لا,لاء,أبداً",
        "city_unknown": "لا أعرف هذه المدينة. مثلاً: أكادير، الدار البيضاء، مدريد، باريس، برشلونة، مرسيليا...",
        "weight_unknown": "يرجى إعطاء الوزن بالكيلوغرام (رقم موجب).",
        "product_unknown": "لا أعرف هذا المنتج. جرب: طماطم، فراولة، حمضيات، أفوكادو، فاصوليا، بطاطس، متنوع.",
        "cold_forced": "❄️ المنتج {product} يتطلب سلسلة التبريد — قمت بتفعيل النقل المبرّد.",
        "ask_customs": "هل ترغب في أن نتولّى التخليص الجمركي والعبور، أم النقل فقط؟ (نعم = نتولّى الجمارك)",
        "ask_urgent": "هل الشحنة مستعجلة / هل تحتاج توصيلاً سريعاً؟",
        "cancelled": "لا مشكلة، لقد ألغيتُ هذا العرض. يمكننا البدء من جديد متى شئت. 👍",
    },
    "es": {
        "greet": "👋 ¡Hola! Soy el asistente de Actos Line Trans. Puedo calcular un presupuesto para frutas y verduras, responder preguntas sobre cadena de frío y aduanas, o ayudarte a seguir un pedido. ¿En qué te ayudo?",
        "ask_pickup": "¿Desde qué ciudad envías?",
        "ask_dest": "¿A qué ciudad de destino?",
        "ask_weight": "¿Cuántos kilogramos?",
        "ask_product": "¿Qué producto transportas? (ej. tomates, fresas, cítricos, aguacate, judías verdes, mixto)",
        "ask_cold": "¿Necesitas transporte refrigerado (cadena de frío)?",
        "ask_name": "¿Cuál es tu nombre?",
        "ask_contact": "¿Cuál es tu número de teléfono?",
        "computing": "Un momento, calculando tu presupuesto...",
        "quote_ready": "Aquí tienes tu presupuesto estimado:",
        "saved": "Tu presupuesto ha sido guardado (#{id}) y nuestro equipo comercial ha sido notificado.",
        "thanks": "¡De nada! ¿Algo más?",
        "fallback": "Soy el asistente de Actos Line Trans 🚚 — solo puedo ayudarte con nuestra empresa y servicios de transporte (presupuestos, plazos, cadena de frío, aduana, seguimiento…). ¿Cómo puedo ayudarte con tu envío? Por ejemplo: «presupuesto tomates Agadir a Madrid 5000 kg» o «¿enviáis a París?»",
        "help": "Puedo: 💰 calcular un presupuesto • 📦 dar información de producto • 🚚 seguir un pedido • 🌐 cambiar idioma. Escribe 'presupuesto' para empezar.",
        "lang_switched": "Idioma cambiado a español.",
        "track_intro": "El seguimiento está simulado por ahora. Abre la página de Seguimiento para ver el envío en el mapa.",
        "missing": "Necesito un poco más de información.",
        "yes_words": "sí,si,vale,claro,por supuesto,ok,por favor",
        "no_words":  "no,nunca,nada",
        "city_unknown": "No conozco esa ciudad. Ejemplos: Agadir, Casablanca, Madrid, París, Barcelona, Marsella...",
        "weight_unknown": "Por favor indica un peso en kilogramos (número positivo).",
        "product_unknown": "No conozco ese producto. Prueba: tomates, fresas, cítricos, aguacate, judías verdes, melones, patatas, mixto.",
        "cold_forced": "❄️ {product} necesita cadena de frío — he activado el transporte refrigerado.",
        "ask_customs": "¿Desea que gestionemos el despacho de aduana y el tránsito, o solo el transporte? (sí = gestionamos la aduana)",
        "ask_urgent": "¿Es urgente este envío / necesita entrega exprés?",
        "cancelled": "Sin problema, he cancelado este presupuesto. Podemos empezar de nuevo cuando quiera. 👍",
    },
}

# FAQ knowledge base. Keys are normalized question keywords; values are answers per language.
FAQ: List[Dict[str, Any]] = [
    {
        "topic": "cold_chain",
        "keywords": {
            "en": ["cold chain", "refrigerated", "reefer", "cooling"],
            "fr": ["chaîne du froid", "chaine du froid", "refrigere", "réfrigéré", "frigo"],
            "ar": ["سلسلة التبريد", "مبرد", "تبريد"],
            "es": ["cadena de frío", "cadena de frio", "refrigerado", "frío"],
        },
        "answer": {
            "en": "Cold chain (chaîne du froid) keeps perishable goods between 2 °C and 8 °C from harvest to delivery. We use reefer trucks for strawberries, avocado, green beans, tomatoes and most berries. It raises the fuel cost because the refrigeration unit burns extra diesel, and it is mandatory for EU import of these products.",
            "fr": "La chaîne du froid maintient les produits périssables entre 2 °C et 8 °C de la récolte à la livraison. Nous utilisons des camions frigorifiques pour les fraises, avocats, haricots verts, tomates et baies. Elle augmente le coût du carburant car le groupe froid consomme plus de gasoil, et c'est obligatoire pour l'import en UE.",
            "ar": "تحافظ سلسلة التبريد على المنتجات سريعة التلف بين 2°م و 8°م من الحصاد إلى التسليم. نستخدم شاحنات مبرّدة للفراولة والأفوكادو والفاصوليا الخضراء والطماطم. ترفع تكلفة الوقود لأن وحدة التبريد تستهلك مزيداً من الديزل، وهي إلزامية للتصدير إلى الاتحاد الأوروبي.",
            "es": "La cadena de frío mantiene los productos perecederos entre 2 °C y 8 °C desde la cosecha hasta la entrega. Usamos camiones frigoríficos para fresas, aguacate, judías verdes, tomates y bayas. Aumenta el coste del combustible porque el equipo de frío consume más gasóleo, y es obligatorio para importar en la UE.",
        },
    },
    {
        "topic": "customs",
        "keywords": {
            "en": ["customs", "diwana", "tariff", "clearance"],
            "fr": ["douane", "douanes", "dédouanement", "dedouanement"],
            "ar": ["جمرك", "جمارك", "ديوانة", "حدود"],
            "es": ["aduana", "aranceles", "frontera"],
        },
        "answer": {
            "en": "For cross-border shipments we can handle customs & transit clearance — a 'diwana' dossier that runs about 500–1500 MAD depending on the goods. Cross-border trips also include the ferry crossing of the Strait. The driver carries the phytosanitary certificates and the EUR.1 form for EU destinations.",
            "fr": "Pour les expéditions internationales, nous pouvons gérer le dédouanement et le transit — un dossier 'diwana' d'environ 500 à 1500 MAD selon la marchandise. Les trajets internationaux incluent aussi la traversée du Détroit en bateau. Le chauffeur emporte les certificats phytosanitaires et le formulaire EUR.1 pour l'UE.",
            "ar": "بالنسبة للشحنات الدولية يمكننا تولّي التخليص الجمركي والعبور — ملف \"ديوانة\" يكلّف نحو 500 إلى 1500 درهم حسب البضاعة. كما تشمل الرحلات الدولية عبور المضيق بالعبّارة. يحمل السائق الشهادات الصحية ونموذج EUR.1 لوجهات الاتحاد الأوروبي.",
            "es": "Para los envíos internacionales podemos encargarnos del despacho de aduana y el tránsito — un expediente 'diwana' de unos 500 a 1500 MAD según la mercancía. Los trayectos internacionales incluyen además el cruce del Estrecho en barco. El conductor lleva los certificados fitosanitarios y el formulario EUR.1 para la UE.",
        },
    },
    {
        "topic": "transit",
        "keywords": {
            "en": ["transit time", "how long", "delivery time", "duration"],
            "fr": ["délai", "delai", "durée", "duree", "combien de temps", "temps de livraison"],
            "ar": ["مدة", "كم تستغرق", "متى يصل"],
            "es": ["plazo", "cuánto tarda", "cuanto tarda", "duración"],
        },
        "answer": {
            "en": "Road transit time depends on the route distance and is estimated from your itinerary (the same basis as your quote). Cross-border trips add customs time at the border.",
            "fr": "Le délai de transport routier dépend de la distance et est estimé à partir de votre itinéraire (la même base que votre devis). Les trajets internationaux ajoutent le temps de douane à la frontière.",
            "ar": "تعتمد مدة النقل البري على مسافة الطريق وتُقدَّر انطلاقاً من مسارك (نفس أساس عرض السعر). تضيف الرحلات الدولية وقت الجمارك عند الحدود.",
            "es": "El plazo de transporte por carretera depende de la distancia y se estima a partir de tu ruta (la misma base que tu presupuesto). Los trayectos internacionales añaden tiempo de aduana en la frontera.",
        },
    },
    {
        "topic": "payment",
        "keywords": {
            "en": ["payment", "invoice"],
            "fr": ["paiement", "payer", "facture"],
            "ar": ["دفع", "أداء", "فاتورة"],
            "es": ["pago", "pagar", "factura"],
        },
        "answer": {
            "en": "We accept bank transfer (RIB) and SEPA for European clients. Invoices are issued in MAD with EUR / USD shown for reference. A 30% deposit is requested for new customers.",
            "fr": "Nous acceptons le virement bancaire (RIB) et SEPA pour les clients européens. Les factures sont en MAD avec EUR/USD indiqués à titre informatif. Un acompte de 30 % est demandé aux nouveaux clients.",
            "ar": "نقبل التحويل البنكي (RIB) و SEPA للعملاء الأوروبيين. الفواتير بالدرهم مع عرض اليورو/الدولار للاطلاع. عربون 30% مطلوب للعملاء الجدد.",
            "es": "Aceptamos transferencia bancaria (RIB) y SEPA para clientes europeos. Las facturas son en MAD con EUR/USD indicados a título informativo. Se pide un anticipo del 30 % a clientes nuevos.",
        },
    },
    {
        "topic": "company",
        "keywords": {
            "en": ["company", "who are you", "actos"],
            "fr": ["entreprise", "société", "qui êtes-vous", "actos"],
            "ar": ["شركة", "من أنتم", "أكتوس"],
            "es": ["empresa", "compañía", "quiénes sois", "actos"],
        },
        "answer": {
            "en": "Actos Line Trans is a logistics company based in Agadir, Morocco, specialized in road export of fresh produce to Morocco and Europe.",
            "fr": "Actos Line Trans est une entreprise de logistique basée à Agadir, spécialisée dans l'export routier de produits frais au Maroc et en Europe.",
            "ar": "Actos Line Trans شركة لوجستيات مقرّها أكادير، متخصّصة في تصدير المنتجات الطازجة عبر البر إلى المغرب وأوروبا.",
            "es": "Actos Line Trans es una empresa de logística con sede en Agadir, especializada en la exportación por carretera de productos frescos a Marruecos y Europa.",
        },
    },
]

# Per-language synonyms that map back to the canonical English product names in PRODUCTS.
PRODUCT_SYNONYMS: Dict[str, str] = {
    # English
    "tomato": "Tomatoes", "tomatoes": "Tomatoes",
    "cherry tomato": "Cherry Tomatoes", "cherry tomatoes": "Cherry Tomatoes",
    "citrus": "Citrus", "orange": "Oranges", "oranges": "Oranges", "mandarin": "Citrus", "lemon": "Citrus",
    "strawberry": "Strawberries", "strawberries": "Strawberries",
    "raspberry": "Raspberries", "raspberries": "Raspberries", "berry": "Raspberries", "berries": "Raspberries",
    "avocado": "Avocado", "avocados": "Avocado",
    "green bean": "Green Beans", "green beans": "Green Beans", "beans": "Green Beans",
    "pepper": "Bell Peppers", "peppers": "Bell Peppers", "bell pepper": "Bell Peppers",
    "zucchini": "Zucchini", "courgette": "Zucchini",
    "cucumber": "Cucumber", "cucumbers": "Cucumber",
    "melon": "Melons", "melons": "Melons",
    "watermelon": "Watermelon",
    "potato": "Potatoes", "potatoes": "Potatoes",
    "onion": "Onions", "onions": "Onions",
    "mixed": "Mixed", "mix": "Mixed",
    # French
    "tomate": "Tomatoes", "tomates": "Tomatoes", "tomate cerise": "Cherry Tomatoes",
    "agrume": "Citrus", "agrumes": "Citrus", "citron": "Citrus", "mandarine": "Citrus",
    "fraise": "Strawberries", "fraises": "Strawberries",
    "framboise": "Raspberries", "framboises": "Raspberries", "myrtille": "Raspberries",
    "avocat": "Avocado", "avocats": "Avocado",
    "haricot vert": "Green Beans", "haricots verts": "Green Beans",
    "poivron": "Bell Peppers", "poivrons": "Bell Peppers",
    "courgette": "Zucchini", "courgettes": "Zucchini",
    "concombre": "Cucumber",
    "melon": "Melons", "pasteque": "Watermelon", "pastèque": "Watermelon",
    "pomme de terre": "Potatoes", "pommes de terre": "Potatoes", "patate": "Potatoes", "patates": "Potatoes",
    "oignon": "Onions", "oignons": "Onions",
    "mélange": "Mixed", "melange": "Mixed", "mélangé": "Mixed",
    # Arabic
    "طماطم": "Tomatoes", "بندورة": "Tomatoes",
    "حمضيات": "Citrus", "برتقال": "Oranges", "ليمون": "Citrus", "يوسفي": "Citrus",
    "فراولة": "Strawberries", "توت": "Raspberries",
    "أفوكادو": "Avocado",
    "فاصوليا": "Green Beans", "لوبيا": "Green Beans",
    "فلفل": "Bell Peppers",
    "كوسة": "Zucchini",
    "خيار": "Cucumber",
    "بطيخ": "Watermelon", "شمام": "Melons",
    "بطاطس": "Potatoes", "بطاطا": "Potatoes",
    "بصل": "Onions",
    "متنوع": "Mixed",
    # Spanish
    "tomate": "Tomatoes", "tomates": "Tomatoes",
    "naranja": "Oranges", "naranjas": "Oranges", "limón": "Citrus", "mandarina": "Citrus", "cítricos": "Citrus", "citricos": "Citrus",
    "fresa": "Strawberries", "fresas": "Strawberries",
    "frambuesa": "Raspberries", "frambuesas": "Raspberries", "arándano": "Raspberries",
    "aguacate": "Avocado", "aguacates": "Avocado",
    "judía verde": "Green Beans", "judia verde": "Green Beans", "judías verdes": "Green Beans", "judias verdes": "Green Beans",
    "pimiento": "Bell Peppers", "pimientos": "Bell Peppers",
    "calabacín": "Zucchini", "calabacin": "Zucchini",
    "pepino": "Cucumber",
    "melón": "Melons", "melon": "Melons", "sandía": "Watermelon", "sandia": "Watermelon",
    "patata": "Potatoes", "patatas": "Potatoes", "papa": "Potatoes",
    "cebolla": "Onions",
    "mixto": "Mixed", "variado": "Mixed",
}

# City synonyms for non-English forms (only the ones that actually differ).
CITY_SYNONYMS: Dict[str, str] = {
    "casa": "Casablanca", "dar el beida": "Casablanca", "الدار البيضاء": "Casablanca", "الدارالبيضاء": "Casablanca",
    "tanger": "Tangier", "tánger": "Tangier", "طنجة": "Tangier",
    "أكادير": "Agadir", "اكادير": "Agadir",
    "marrakech": "Marrakech", "مراكش": "Marrakech",
    "fès": "Fes", "fes": "Fes", "فاس": "Fes",
    "rabat": "Rabat", "الرباط": "Rabat",
    "oujda": "Oujda", "وجدة": "Oujda",
    "meknès": "Meknes", "meknes": "Meknes", "مكناس": "Meknes",
    "kénitra": "Kenitra", "kenitra": "Kenitra", "القنيطرة": "Kenitra",
    "tétouan": "Tetouan", "tetouan": "Tetouan", "تطوان": "Tetouan",
    "paris": "Paris", "parís": "Paris", "باريس": "Paris",
    "madrid": "Madrid", "مدريد": "Madrid",
    "barcelone": "Barcelona", "barcelona": "Barcelona", "برشلونة": "Barcelona",
    "marseille": "Marseille", "marsella": "Marseille", "مرسيليا": "Marseille",
    "bruxelles": "Brussels", "brussels": "Brussels", "bruselas": "Brussels",
    "amsterdam": "Amsterdam",
    "berlin": "Berlin", "berlín": "Berlin",
    "milan": "Milan", "milán": "Milan",
    "lisbonne": "Lisbon", "lisboa": "Lisbon",
    "londres": "London", "london": "London",
    "rome": "Rome", "roma": "Rome",
    "vienne": "Vienna", "vienna": "Vienna", "viena": "Vienna",
    "munich": "Munich", "münich": "Munich",
    "francfort": "Frankfurt", "frankfurt": "Frankfurt",
    "lyon": "Lyon",
    "valence": "Valencia", "valencia": "Valencia",
    "séville": "Seville", "seville": "Seville", "sevilla": "Seville",
    "porto": "Porto",
    "dublin": "Dublin", "dublín": "Dublin",
    "zurich": "Zurich", "zúrich": "Zurich",
    "genève": "Geneva", "geneve": "Geneva", "geneva": "Geneva", "ginebra": "Geneva",
}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _strip_diacritics(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def normalize(text: str) -> str:
    """Lowercase + strip diacritics + collapse whitespace. Arabic letters are kept."""
    if not text:
        return ""
    out = text.strip().lower()
    out = _strip_diacritics(out)
    out = re.sub(r"\s+", " ", out)
    return out

def _word_in(token: str, norm_text: str) -> bool:
    """Whole-word containment for Latin tokens; substring for non-Latin (Arabic).

    Both `token` and `norm_text` must already be normalized (lowercase, no
    diacritics). This prevents substring false positives such as 'rome' inside
    'chrome', 'paris' inside 'comparison', or the 3-letter canonical 'Fes'
    inside 'manifest' — the bug that let off-topic text fake a city/product.
    """
    if not token:
        return False
    if token.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", norm_text) is not None
    return token in norm_text

def _detect_unsupported(text: str) -> Optional[str]:
    """Return 'mode' / 'cargo' if the user asks for a service we don't provide
    (air/sea/rail freight, or non-produce cargo like live animals/passengers)."""
    n = normalize(text)
    for kw in kb.UNSUPPORTED_MODES:
        if _word_in(normalize(kw), n):
            return "mode"
    for kw in kb.UNSUPPORTED_CARGO:
        if _word_in(normalize(kw), n):
            return "cargo"
    return None

def _detect_foreign_place(text: str) -> bool:
    """True if the message names a place we positively know is out-of-network
    (kb.FOREIGN_PLACES) — e.g. New York, Dubai, Tokyo."""
    n = normalize(text)
    for place in kb.FOREIGN_PLACES:
        pn = normalize(place)
        if pn and _word_in(pn, n):
            return True
    return False

def _has_offtopic_marker(text: str) -> bool:
    """True if the message contains a clearly off-topic marker (weather, capital
    of, recipe...). Lets us tell a route question ('ship to Tokyo') apart from a
    general-knowledge one ('capital of Japan') that merely names a place."""
    n = normalize(text)
    return any(normalize(m) in n for m in kb.OUT_OF_SCOPE_MARKERS)

def detect_language(text: str) -> str:
    """Return one of en / fr / ar / es. Conservative heuristic, not a real LangID.

    Uses WHOLE-WORD matching (not substrings) so that e.g. 'Test' is not read as the
    French 'est', and 'Madrid' is not read as anything. Returns 'en' when nothing
    matches, so a neutral message (a name, a phone number) never flips the language.
    """
    if not text:
        return "en"
    # Arabic — character set is unmistakable
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    n = normalize(text)
    words = set(re.findall(r"[a-zñçàâéèêëîïôûùü]+", n))

    FR = {"le", "la", "les", "des", "un", "une", "est", "vers", "je", "veux", "voudrais",
          "pour", "oui", "non", "ville", "bonjour", "bonsoir", "salut", "merci", "devis",
          "fraise", "fraises", "tomate", "tomates", "haricot", "melange", "expedier", "expeddier"}
    ES = {"el", "los", "las", "una", "esta", "quiero", "quisiera", "para", "si", "ciudad",
          "hola", "gracias", "buenos", "dias", "presupuesto", "fresa", "fresas", "judia",
          "mixto", "enviar", "envio"}
    EN = {"the", "a", "an", "from", "to", "want", "please", "city", "need", "hello", "hi",
          "hey", "thanks", "thank", "quote", "ship", "shipping", "tomato", "strawberry"}

    fr_hits = len(words & FR)
    es_hits = len(words & ES)
    en_hits = len(words & EN)
    best = max(("en", en_hits), ("fr", fr_hits), ("es", es_hits), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "en"


# -----------------------------------------------------------------------------
# Entity extraction
# -----------------------------------------------------------------------------

def extract_weight(text: str) -> Optional[float]:
    """Find a weight in kilograms. Tons are converted ('2 t' -> 2000)."""
    if not text:
        return None
    n = normalize(text)
    # tons
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:t|ton|tons|tonne|tonnes|طن)", n)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000.0
    # kg
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kg|kgs|kilo|kilos|kilogram|kilogramme|kilogrammes|kilogramo|كغ|كيلو)", n)
    if m:
        return float(m.group(1).replace(",", "."))
    # bare number near 'weight' word
    m = re.search(r"(?:weight|poids|peso|وزن)\D{0,5}(\d+(?:[.,]\d+)?)", n)
    if m:
        return float(m.group(1).replace(",", "."))
    return None

def extract_palettes(text: str) -> Optional[int]:
    """Find a number of pallets, e.g. '12 palettes', '5 palets', '3 بالته'."""
    if not text:
        return None
    n = normalize(text)
    m = re.search(r"(\d+)\s*(?:palettes?|palets?|pallets?|pallet|بالته|بالطات|palés?|palé)", n)
    if m:
        return int(m.group(1))
    return None

def detect_fragile(text: str) -> bool:
    n = normalize(text)
    return any(w in n for w in ["fragile", "fragiles", "cassable", "frágil", "fragil", "قابل للكسر", "هش"])

def detect_dangerous(text: str) -> bool:
    # Word boundaries so 'adr' doesn't match inside 'Madrid', etc.
    n = normalize(text)
    if re.search(r"\b(dangerous|dangereux|dangereuse|peligroso|adr|hazard|hazardous)\b", n):
        return True
    return any(w in text for w in ["خطير", "خطر", "مواد خطرة"])

def extract_product(text: str, available_products: List[str]) -> Optional[str]:
    if not text:
        return None
    n = normalize(text)
    # First try canonical product names (whole-word so 'mixed' doesn't match
    # 'mixed feelings' and 'orange' doesn't match 'orange juice business').
    for p in available_products:
        if _word_in(p.lower(), n):
            return p
    # Then synonyms (longest match wins)
    matches = []
    for syn, canon in PRODUCT_SYNONYMS.items():
        if _word_in(normalize(syn), n):
            matches.append((len(syn), canon))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]

def extract_cities(text: str, available_cities: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Find pickup and destination using 'from X to Y' patterns + synonyms.

    Returns (pickup, destination). Either may be None.
    """
    if not text:
        return None, None
    raw = text
    n = normalize(text)

    # Build a flat lookup of all city tokens (canonical + synonyms)
    canonical = {c.lower(): c for c in available_cities}
    syns = {normalize(k): v for k, v in CITY_SYNONYMS.items() if v in available_cities}
    syns.update({c.lower(): c for c in available_cities})

    def find_in(s: str) -> Optional[str]:
        s_norm = normalize(s)
        # Whole-word match so 'rome' inside 'chrome' or 'paris' inside
        # 'comparison' can't fake a city. Arabic synonyms fall back to substring
        # inside _word_in (Arabic doesn't have the in-word collision problem).
        for k, v in CITY_SYNONYMS.items():
            if v in available_cities and _word_in(normalize(k), s_norm):
                return v
        for token, canon in sorted(syns.items(), key=lambda x: -len(x[0])):
            if token and _word_in(token, s_norm):
                return canon
        return None

    pickup = dest = None
    # Patterns: "from A to B", "de A à B", "de A a B", "من A إلى B"
    patterns = [
        r"from\s+(.+?)\s+(?:to|->|→)\s+(.+?)(?:\s|$|[,.!?])",
        r"de\s+(.+?)\s+(?:vers|à|a|->)\s+(.+?)(?:\s|$|[,.!?])",
        r"desde\s+(.+?)\s+(?:a|hasta|->)\s+(.+?)(?:\s|$|[,.!?])",
        r"من\s+(.+?)\s+(?:إلى|الى|->)\s+(.+?)(?:\s|$|[,.!?])",
        r"(.+?)\s+(?:to|->|→|vers|à|إلى)\s+(.+?)(?:\s|$|[,.!?])",
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            pickup = find_in(m.group(1))
            dest = find_in(m.group(2))
            if pickup and dest:
                break

    # Fallback: scan for any single city occurrence
    if not pickup and not dest:
        c = find_in(raw)
        if c:
            # We don't know if it's pickup or destination yet — caller decides by context
            pickup = c

    return pickup, dest


# -----------------------------------------------------------------------------
# Intent classification
# -----------------------------------------------------------------------------

INTENT_PATTERNS = {
    "greet":      [r"\b(hello|hi|hey|good morning|good afternoon|salut|bonjour|bonsoir|hola|buenos dias|مرحبا|أهلا|السلام)\b"],
    "thanks":     [r"\b(thanks|thank you|merci|gracias|شكرا)\b"],
    "help":       [r"\b(help|aide|aidez|ayuda|مساعدة)\b"],
    "quote":      [r"\b(quote|estimate|price|cost|devis|tarif|prix|presupuesto|precio|سعر|عرض|تكلفة)\b"],
    "track":      [r"\b(track|tracking|where is|suivi|suivre|seguir|seguimiento|أين|تتبع)\b"],
    "product":    [r"\b(product|products|catalog|catalogue|produit|producto|productos|منتج|منتجات)\b"],
    "set_lang_en": [r"\b(english|in english|انجليزية|inglés|inglese)\b"],
    "set_lang_fr": [r"\b(french|en français|en francais|francais|français|francés|francaise|الفرنسية)\b"],
    "set_lang_ar": [r"\b(arabic|arabe|árabe|العربية|بالعربية)\b"],
    "set_lang_es": [r"\b(spanish|español|espanol|en espanol|en español|الإسبانية|اسبانية|espagnol)\b"],
    "cancel":      [r"\b(cancel|reset|restart|start over|annuler|annule|recommencer|réinitialiser|cancelar|empezar de nuevo|إلغاء|الغاء|إعادة)\b"],
}

def classify_intent(text: str) -> str:
    n = normalize(text)
    raw = text.lower()
    for intent, pats in INTENT_PATTERNS.items():
        for p in pats:
            if re.search(p, n) or re.search(p, raw):
                return intent
    return "fallback"


# -----------------------------------------------------------------------------
# Session memory (kept in-process; fine for a class demo)
# -----------------------------------------------------------------------------

SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_session(session_id: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    if not session_id or session_id not in SESSIONS:
        session_id = uuid.uuid4().hex[:12]
        SESSIONS[session_id] = {
            "lang": "en",
            "slots": {},          # pickup, destination, weight, product, refrigerated, name, contact
            "awaiting": None,     # which slot we're currently waiting for
        }
    return session_id, SESSIONS[session_id]


# -----------------------------------------------------------------------------
# Dialog manager — main entry point used by /api/chatbot
# -----------------------------------------------------------------------------

# next slot to ask, in order (follows the 5-step flow from the project spec:
# itinerary -> weight -> nature -> customs -> urgency, then contact details)
SLOT_ORDER = ["pickup", "destination", "weight", "product", "refrigerated",
              "customs_service", "urgent", "name", "contact"]
SLOT_PROMPTS = {
    "pickup":          "ask_pickup",
    "destination":     "ask_dest",
    "weight":          "ask_weight",
    "product":         "ask_product",
    "refrigerated":    "ask_cold",
    "customs_service": "ask_customs",
    "urgent":          "ask_urgent",
    "name":            "ask_name",
    "contact":         "ask_contact",
}

def _next_missing_slot(slots: Dict[str, Any]) -> Optional[str]:
    for s in SLOT_ORDER:
        if slots.get(s) in (None, "", []):
            return s
    return None

def handle_message(
    text: str,
    session_id: Optional[str],
    available_cities: List[str],
    available_products: List[str],
    products_meta: Dict[str, Dict[str, Any]],
    forced_lang: Optional[str] = None,
) -> Dict[str, Any]:
    """Main bot reply function. Returns a dict ready to JSON-encode for the frontend."""
    session_id, sess = get_session(session_id)

    # Language: caller can force it (UI selector) or we auto-detect.
    if forced_lang and forced_lang in STRINGS:
        sess["lang"] = forced_lang
    else:
        lang = detect_language(text)
        # Don't bounce languages on every utterance, only when confident or first turn.
        if lang == "ar" or sess["lang"] == "en":
            sess["lang"] = lang
    L = sess["lang"]
    S = STRINGS[L]

    # -------- 1) Detect language switch intents up front
    intent = classify_intent(text)
    if intent == "set_lang_en": sess["lang"] = "en"; return {"reply": STRINGS["en"]["lang_switched"], "intent": "set_lang", "session_id": session_id, "lang": "en"}
    if intent == "set_lang_fr": sess["lang"] = "fr"; return {"reply": STRINGS["fr"]["lang_switched"], "intent": "set_lang", "session_id": session_id, "lang": "fr"}
    if intent == "set_lang_ar": sess["lang"] = "ar"; return {"reply": STRINGS["ar"]["lang_switched"], "intent": "set_lang", "session_id": session_id, "lang": "ar"}
    if intent == "set_lang_es": sess["lang"] = "es"; return {"reply": STRINGS["es"]["lang_switched"], "intent": "set_lang", "session_id": session_id, "lang": "es"}

    # -------- Edge case: user wants to abandon / restart the quote
    if intent == "cancel":
        reset_session(session_id)
        return {"reply": S["cancelled"], "intent": "cancel", "session_id": session_id, "lang": L}

    # -------- 2) Try FAQ — but NOT while we're waiting for a slot answer,
    # otherwise an answer like "yes, handle customs" gets hijacked by the customs FAQ.
    faq_answer, faq_topic = match_faq(text, L)
    # A generic price word ('cost'/'price') in an informational question must NOT
    # hijack an FAQ into the quote flow ('how much does cold chain cost?'). The
    # quote flow only wins if the user EXPLICITLY asks to quote, or states a
    # weight (a real shipment).
    _explicit_quote = bool(re.search(
        r"\b(quote|estimate|estimation|devis|presupuesto|cotizacion|estimacion)\b", normalize(text))) \
        or ("عرض" in text)
    _wants_quote = _explicit_quote or (extract_weight(text) is not None)
    if faq_answer and not _wants_quote and not sess.get("awaiting"):
        # Geography gate: don't leak the transit/customs tables for a city we
        # don't serve. If the user named an out-of-network destination, refuse.
        if faq_topic in ("transit", "customs") and _mentions_unserved_place(text, available_cities):
            return {"reply": kb.OUT_OF_NETWORK.get(L, kb.OUT_OF_NETWORK["en"]),
                    "intent": "faq_unserved", "session_id": session_id, "lang": L}
        faq_result = {"reply": faq_answer, "intent": "faq", "session_id": session_id,
                      "lang": L, "faq_topic": faq_topic}
        # For transit, surface the cities so the endpoint can compute the real
        # lead time from the distance model (single source of truth).
        if faq_topic == "transit":
            pk, ds = extract_cities(text, available_cities)
            if ds:
                faq_result["faq_dest"] = ds
                if pk and pk != ds:
                    faq_result["faq_origin"] = pk
            elif pk:
                faq_result["faq_dest"] = pk
        return faq_result

    # -------- Unsupported-service guard: we only do ROAD freight of fruits &
    # vegetables. Refuse air/sea/rail or non-produce cargo (live animals,
    # passengers, electronics...) deterministically, before any quote starts.
    if _detect_unsupported(text):
        return {"reply": kb.UNSUPPORTED_SERVICE.get(L, kb.UNSUPPORTED_SERVICE["en"]),
                "intent": "refused_unsupported", "session_id": session_id, "lang": L}

    # -------- Out-of-network destination guard: a clearly unserved place
    # (New York, Dubai...) in a shipping context gets a graceful coverage reply
    # in CODE — never the generic LLM refusal. General-knowledge questions that
    # merely name a place ("capital of Japan") are excluded by the marker check.
    if _detect_foreign_place(text) and not _has_offtopic_marker(text):
        return {"reply": kb.OUT_OF_NETWORK.get(L, kb.OUT_OF_NETWORK["en"]),
                "intent": "refused_out_of_network", "session_id": session_id, "lang": L}

    # Pre-extract shipment entities so a greeting that ALSO carries details
    # ("Bonjour, je veux un devis 6000 kg d'Agadir vers Paris") starts the quote
    # instead of only saying hello. Same idea protects thanks/help.
    pickup, dest = extract_cities(text, available_cities)
    weight = extract_weight(text)
    product = extract_product(text, available_products)
    _qpat = INTENT_PATTERNS["quote"][0]
    quote_signal = bool(
        re.search(_qpat, normalize(text)) or re.search(_qpat, text.lower())
        or pickup or dest or weight is not None or product
    )

    # -------- 3) Greeting / thanks / help / track / product without slot-filling
    if intent == "greet" and not sess.get("awaiting") and not quote_signal:
        return {"reply": S["greet"], "intent": "greet", "session_id": session_id, "lang": L}
    if intent == "thanks" and not quote_signal:
        return {"reply": S["thanks"], "intent": "thanks", "session_id": session_id, "lang": L}
    if intent == "help" and not quote_signal:
        return {"reply": S["help"], "intent": "help", "session_id": session_id, "lang": L}
    if intent == "track":
        return {"reply": S["track_intro"], "intent": "track", "session_id": session_id, "lang": L,
                "action": "open_tracking"}
    if intent == "product":
        # Return a list of products in the user's language by listing icons
        names = ", ".join([f"{products_meta[p]['icon']} {p}" for p in available_products[:10]])
        return {"reply": f"{names}…", "intent": "product", "session_id": session_id, "lang": L}

    # -------- 4) Quote slot-filling (the heart of the bot)
    slots = sess["slots"]

    # If we were waiting for a specific slot, route the value there first.
    awaiting = sess.get("awaiting")
    if awaiting == "pickup" and pickup is None and dest is not None:
        # User typed a single city while we asked for pickup -> treat as pickup
        pickup, dest = dest, None
    if awaiting == "pickup" and pickup:
        slots["pickup"] = pickup
    elif awaiting == "destination" and (pickup or dest):
        slots["destination"] = dest or pickup
    elif awaiting == "weight" and weight is not None:
        slots["weight"] = weight
    elif awaiting == "product" and product:
        slots["product"] = product
    elif awaiting == "refrigerated":
        yn = _yes_no(text, L)
        if yn is not None:
            slots["refrigerated"] = yn
    elif awaiting == "customs_service":
        yn = _yes_no(text, L)
        if yn is None:
            nlow = normalize(text)
            if (any(_word_in(k, nlow) for k in ["only transport", "transport only", "just transport",
                                        "uniquement", "seulement", "solo transporte", "transporte solo"])
                    or "النقل فقط" in text or "فقط" in text):
                yn = False
            elif (any(_word_in(k, nlow) for k in ["customs", "douane", "dedouanement", "clearance",
                                          "transit", "handle", "gerer", "aduana", "despacho"])
                  or any(k in text for k in ["جمارك", "تخليص", "ديوانة"])):
                yn = True
        if yn is not None:
            slots["customs_service"] = yn
    elif awaiting == "urgent":
        yn = _yes_no(text, L)
        if yn is None:
            nlow = normalize(text)
            if (any(_word_in(k, nlow) for k in ["not urgent", "no rush", "standard", "normal",
                                        "pas urgent", "pas presse", "sin prisa", "no urgente"])
                    or "عادي" in text or "غير مستعجل" in text):
                yn = False
            elif (any(_word_in(k, nlow) for k in ["urgent", "asap", "express", "fast", "quick", "rush",
                                          "presse", "rapide", "urgente", "rapido", "prisa"])
                  or any(k in text for k in ["مستعجل", "عاجل", "سريع"])):
                yn = True
        if yn is not None:
            slots["urgent"] = yn
    elif awaiting == "name":
        clean = text.strip()
        if clean and len(clean) <= 80:
            slots["name"] = clean
    elif awaiting == "contact":
        m = re.search(r"[+\d][\d\s().-]{6,}\d", text)
        if m:
            slots["contact"] = m.group(0).strip()
    else:
        # Free-form: only START a quote on a STRONG signal — an explicit quote
        # word, a full route (both cities), or a weight. A lone city or product
        # word ('I love Paris', 'mixed feelings') must NOT auto-launch a quote;
        # it falls through to the scope gate / LLM instead.
        strong_quote_signal = (intent == "quote") or bool(pickup and dest) or (weight is not None)
        if strong_quote_signal:
            if pickup and not slots.get("pickup"):
                slots["pickup"] = pickup
            if dest and not slots.get("destination"):
                slots["destination"] = dest
            if weight and not slots.get("weight"):
                slots["weight"] = weight
            if product and not slots.get("product"):
                slots["product"] = product

    # Optional "nature of goods" details — detected any time the user mentions them,
    # they refine the quote but never block the conversation (they have safe defaults).
    pal = extract_palettes(text)
    if pal is not None:
        slots["palettes"] = pal
    if detect_fragile(text):
        slots["fragile"] = True
    if detect_dangerous(text):
        slots["dangerous"] = True

    # Auto-cold for products that require it
    if slots.get("product") and slots.get("refrigerated") is None:
        meta = products_meta.get(slots["product"], {})
        if meta.get("requires_cold"):
            slots["refrigerated"] = True

    # Did the user ask for a quote OR are we mid-quote?
    quote_in_flight = intent == "quote" or sess.get("awaiting") in SLOT_ORDER or any(slots.get(s) for s in SLOT_ORDER)

    if not quote_in_flight:
        return {"reply": S["fallback"], "intent": "fallback", "session_id": session_id, "lang": L}

    next_slot = _next_missing_slot(slots)
    if next_slot is None:
        # All slots full -> caller will compute the quote and call /send-email
        sess["awaiting"] = None
        return {
            "reply": S["computing"],
            "intent": "quote_complete",
            "session_id": session_id,
            "lang": L,
            "slots": dict(slots),
        }

    # Some slots filled, ask for the next one
    sess["awaiting"] = next_slot
    msg = S[SLOT_PROMPTS[next_slot]]
    if next_slot == "refrigerated" and slots.get("product"):
        meta = products_meta.get(slots["product"], {})
        if meta.get("requires_cold"):
            msg = S["cold_forced"].format(product=slots["product"])
            slots["refrigerated"] = True
            sess["awaiting"] = _next_missing_slot(slots)
            if sess["awaiting"]:
                msg += " " + S[SLOT_PROMPTS[sess["awaiting"]]]
            else:
                return {"reply": msg, "intent": "quote_complete", "session_id": session_id, "lang": L,
                        "slots": dict(slots)}

    return {
        "reply": msg,
        "intent": "ask_slot",
        "slot": next_slot,
        "session_id": session_id,
        "lang": L,
        "slots": dict(slots),
    }


def _yes_no(text: str, lang: str) -> Optional[bool]:
    """Whole-word yes/no detection. Single Latin words are matched as whole words
    (so 'no' does NOT match inside 'not'); phrases and Arabic match as substrings."""
    n = normalize(text)
    words = set(re.findall(r"[\w']+", n, re.UNICODE))

    def hit(w: str) -> bool:
        if not w:
            return False
        if " " in w:          # multi-word phrase
            return w in n
        if w.isascii():       # single Latin word -> whole word only
            return w in words
        return w in n         # Arabic etc. -> substring

    yes = [w.strip() for w in STRINGS[lang]["yes_words"].split(",")]
    no  = [w.strip() for w in STRINGS[lang]["no_words"].split(",")]
    if any(hit(w) for w in yes):
        return True
    if any(hit(w) for w in no):
        return False
    return None


def match_faq(text: str, lang: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (answer, topic) for the best-matching FAQ entry, or (None, None).

    `topic` ('cold_chain' / 'customs' / 'transit' / 'payment' / 'company') lets
    the caller geo-gate the geography-sensitive answers.
    """
    n = normalize(text)
    best = None
    best_topic = None
    best_hits = 0
    for entry in FAQ:
        hits = 0
        for kw in entry["keywords"].get(lang, []):
            kn = normalize(kw)
            if kn and _word_in(kn, n):
                hits += 1
        # also check Arabic against raw text (no diacritic strip applied)
        if lang == "ar":
            for kw in entry["keywords"].get("ar", []):
                if kw in text:
                    hits += 1
        if hits > best_hits:
            best_hits = hits
            best = entry["answer"].get(lang) or entry["answer"]["en"]
            best_topic = entry.get("topic")
    if best_hits >= 1:
        return best, best_topic
    return None, None


def _mentions_unserved_place(text: str, available_cities: List[str]) -> bool:
    """True if the message refers to a destination we do NOT serve.

    Used to stop transit/customs FAQ answers from leaking the route/customs
    tables for cities outside the 31-city network (New York, Dubai, ...).
    Conservative on purpose: if a network city is present we never flag it, and
    we only flag a place we positively recognise as out-of-network.
    """
    # A network city is present -> served context, answer normally.
    pickup, dest = extract_cities(text, available_cities)
    if pickup or dest:
        return False
    n = normalize(text)
    for place in kb.FOREIGN_PLACES:
        pn = normalize(place)
        if pn and _word_in(pn, n):
            return True
    return False


def reset_session(session_id: str):
    if session_id in SESSIONS:
        SESSIONS[session_id]["slots"] = {}
        SESSIONS[session_id]["awaiting"] = None
