import streamlit as st
from pymongo import MongoClient
import pandas as pd

# ─── Configuración de página ───
st.set_page_config(page_title="Restaurantes NYC", page_icon="🍽️", layout="wide")

st.title("🍽️ Restaurantes NYC — Sample Restaurants")
st.caption("Consulta restaurantes y su neighborhood asociado vía MongoDB Atlas")

# ─── Conexión a MongoDB Atlas vía secrets ───
# Configurado en .streamlit/secrets.toml
try:
    mongo_uri = st.secrets["mongo"]["uri"]
except KeyError:
    st.error(
        "❌ No se encontró el secreto `mongo.uri`. "
        "Crea el archivo `.streamlit/secrets.toml` con:\n\n"
        "```\n[mongo]\nuri = \"mongodb+srv://usuario:password@cluster.xxxxx.mongodb.net/\"\n```"
    )
    st.stop()

with st.sidebar:
    st.header("🔌 MongoDB Atlas")
    st.markdown(
        "**Conexión:** vía `st.secrets`\n\n"
        "**Requisitos:**\n"
        "- Dataset `sample_restaurants` cargado\n"
        "- Índice `2dsphere` en `neighborhoods.geometry`"
    )

# ─── Conectar ───
@st.cache_resource
def get_client(uri):
    return MongoClient(uri)

try:
    client = get_client(mongo_uri)
    db = client["sample_restaurants"]
    col_restaurants = db["restaurants"]
    col_neighborhoods = db["neighborhoods"]
    # Test de conexión
    client.admin.command("ping")
    st.sidebar.success("✅ Conectado a MongoDB Atlas")
except Exception as e:
    st.error(f"❌ Error de conexión: {e}")
    st.stop()

# ─── Asegurar índice geoespacial ───
try:
    col_neighborhoods.create_index([("geometry", "2dsphere")])
except Exception:
    pass

# ─── Búsqueda ───
st.markdown("---")
col1, col2 = st.columns([3, 1])

with col1:
    nombre_busqueda = st.text_input(
        "🔍 Buscar restaurante por nombre",
        placeholder="Ej: Riviera, Wendy, Morris Park"
    )

with col2:
    limite = st.selectbox("Resultados máx.", [5, 10, 20, 50], index=1)

if not nombre_busqueda:
    st.info("Escribe un nombre (o parte del nombre) de un restaurante para buscar.")
    st.stop()

# ─── Consulta de restaurantes (búsqueda parcial, case-insensitive) ───
query = {"name": {"$regex": nombre_busqueda, "$options": "i"}}
restaurantes = list(col_restaurants.find(query).limit(limite))

if not restaurantes:
    st.warning(f"No se encontraron restaurantes con el nombre **'{nombre_busqueda}'**.")
    st.stop()

st.success(f"Se encontraron **{len(restaurantes)}** restaurante(s)")

# ─── Función para obtener el neighborhood geoespacialmente ───
def get_neighborhood(coord):
    """Dado un [lng, lat], busca en qué neighborhood cae el punto."""
    if not coord or len(coord) < 2:
        return "Sin coordenadas"
    try:
        result = col_neighborhoods.find_one({
            "geometry": {
                "$geoIntersects": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": coord
                    }
                }
            }
        })
        if result:
            return result.get("name", "Desconocido")
        return "Fuera de cobertura"
    except Exception as e:
        return f"Error: {e}"

# ─── Construir tabla de resultados ───
resultados = []
for r in restaurantes:
    coord = r.get("address", {}).get("coord", [])
    neighborhood = get_neighborhood(coord)

    # Obtener última calificación
    grades = r.get("grades", [])
    ultima_nota = grades[0].get("grade", "N/A") if grades else "N/A"
    ultimo_score = grades[0].get("score", "N/A") if grades else "N/A"

    resultados.append({
        "Restaurante": r.get("name", "—"),
        "Cocina": r.get("cuisine", "—"),
        "Borough": r.get("borough", "—"),
        "Neighborhood": neighborhood,
        "Dirección": f"{r.get('address', {}).get('building', '')} {r.get('address', {}).get('street', '')}".strip(),
        "Última Nota": ultima_nota,
        "Último Score": ultimo_score,
        "Longitud": coord[0] if len(coord) >= 2 else None,
        "Latitud": coord[1] if len(coord) >= 2 else None,
    })

df = pd.DataFrame(resultados)

# ─── Mostrar tabla ───
st.markdown("### 📋 Resultados")
st.dataframe(df, use_container_width=True, hide_index=True)

# ─── Mapa ───
df_map = df.dropna(subset=["Latitud", "Longitud"]).copy()
df_map = df_map.rename(columns={"Latitud": "latitude", "Longitud": "longitude"})

if not df_map.empty:
    st.markdown("### 🗺️ Ubicación en el mapa")
    st.map(df_map[["latitude", "longitude"]])

# ─── Detalle expandible por restaurante ───
st.markdown("### 📝 Detalle por restaurante")
for i, r in enumerate(restaurantes):
    nombre = r.get("name", "—")
    with st.expander(f"**{nombre}** — {r.get('cuisine', '')} ({r.get('borough', '')})"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Neighborhood:** {resultados[i]['Neighborhood']}")
            st.markdown(f"**Dirección:** {resultados[i]['Dirección']}")
            st.markdown(f"**Borough:** {r.get('borough', '—')}")
            st.markdown(f"**Cocina:** {r.get('cuisine', '—')}")
            st.markdown(f"**Restaurant ID:** {r.get('restaurant_id', '—')}")

        with c2:
            grades = r.get("grades", [])
            if grades:
                st.markdown("**Historial de calificaciones:**")
                grade_data = []
                for g in grades[:10]:
                    grade_data.append({
                        "Fecha": g.get("date", "").strftime("%Y-%m-%d") if hasattr(g.get("date", ""), "strftime") else str(g.get("date", "")),
                        "Nota": g.get("grade", "—"),
                        "Score": g.get("score", "—"),
                    })
                st.dataframe(pd.DataFrame(grade_data), hide_index=True)
            else:
                st.info("Sin historial de calificaciones")
