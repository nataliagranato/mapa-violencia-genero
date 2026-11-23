import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./style.css";

const QUICK_EXIT_URL = "https://www.google.com/search?q=previsao+do+tempo+belo+horizonte";

function triggerQuickExit() {
  window.location.replace(QUICK_EXIT_URL);
}

document.getElementById("quick-exit").addEventListener("click", triggerQuickExit);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    triggerQuickExit();
  }
});

// Centralizado em Minas Gerais
const map = L.map("map", {
  center: [-18.5122, -44.555],
  zoom: 6,
  minZoom: 5,
  maxZoom: 13,
  attributionControl: false,
});

const statusEl = document.getElementById("status-msg");
const tipoEl = document.getElementById("select-tipo");
const anoEl = document.getElementById("select-ano");
const searchEl = document.getElementById("search-municipio");
const datalistEl = document.getElementById("municipios-list");
const panelTitleEl = document.getElementById("panel-title");
const panelBodyEl = document.getElementById("panel-body");

let geoLayer = null;
let cachedMalha = null;
let municipiosPorNome = new Map();
let layersPorCodigo = new Map();

function corPorValor(registro) {
  const metrica = registro?.taxa_100k ?? registro?.valor_absoluto;
  if (metrica === null || metrica === undefined) return "#cbd5e1";
  if (metrica >= 50) return "#581c87";
  if (metrica >= 15) return "#7e22ce";
  if (metrica >= 5) return "#a855f7";
  if (metrica > 0) return "#d8b4fe";
  return "#e2e8f0";
}

async function carregarMalhaMG() {
  if (cachedMalha) return cachedMalha;
  const resp = await fetch("/malhas/mg_municipios.geojson");
  if (!resp.ok) {
    throw new Error(
      "Malha de MG não encontrada. Rode 'python3 scripts/sync_ibge_mg.py' primeiro."
    );
  }
  cachedMalha = await resp.json();
  return cachedMalha;
}

async function carregarDetalhesMunicipio(codigoIBGE) {
  panelTitleEl.textContent = "Carregando...";
  panelBodyEl.innerHTML = "";

  const resp = await fetch(`/api/municipio/${encodeURIComponent(codigoIBGE)}`);
  if (!resp.ok) {
    panelTitleEl.textContent = `Código IBGE ${codigoIBGE}`;
    panelBodyEl.innerHTML = "<p>Não foi possível carregar os detalhes deste município.</p>";
    return;
  }

  const dados = await resp.json();
  panelTitleEl.textContent = `${dados.nome} — MG`;

  const metaHTML = `
    <p>
      <strong>Mesorregião:</strong> ${dados.mesorregiao ?? "n/d"}<br />
      <strong>Microrregião:</strong> ${dados.microrregiao ?? "n/d"}
    </p>
  `;

  let seriesHTML =
    "<p>Ainda não há indicadores carregados para este município. Importe os CSVs da SEJUSP-MG ou SES-MG usando <code>scripts/import_indicadores.py</code>.</p>";
  if (dados.series && dados.series.length > 0) {
    const items = dados.series
      .map(
        (s) => `
        <li>
          <strong>${s.ano} · ${s.tipo}</strong><br />
          Registros: ${s.valor_absoluto} | Taxa/100k: ${s.taxa_100k ?? "n/d"}<br />
          <a href="${s.fonte_url}" target="_blank" rel="noopener noreferrer">${s.fonte_nome}</a>
        </li>`
      )
      .join("");
    seriesHTML = `<h3>Série histórica</h3><ul class="series-list">${items}</ul>`;
  }

  let apoioHTML = "";
  if (dados.rede_apoio && dados.rede_apoio.length > 0) {
    const apoios = dados.rede_apoio
      .map(
        (a) => `
        <li>
          <strong>${a.nome}</strong> (${a.categoria})<br />
          ${a.endereco ?? ""}${a.telefone ? ` · Tel: ${a.telefone}` : ""}
        </li>`
      )
      .join("");
    apoioHTML = `<h3>Rede de apoio local</h3><ul class="series-list">${apoios}</ul>`;
  }

  panelBodyEl.innerHTML = metaHTML + seriesHTML + apoioHTML;
}

function preencherBusca(itens) {
  municipiosPorNome = new Map();
  datalistEl.innerHTML = "";
  for (const item of itens) {
    municipiosPorNome.set(item.nome.toLowerCase(), item.codigo_ibge);
    const opt = document.createElement("option");
    opt.value = item.nome;
    datalistEl.appendChild(opt);
  }
}

async function atualizarMapa() {
  const tipo = tipoEl.value;
  const ano = anoEl.value;
  statusEl.textContent = "Consultando SQLite de MG...";

  try {
    const [malha, respApi] = await Promise.all([
      carregarMalhaMG(),
      fetch(`/api/mapa?ano=${encodeURIComponent(ano)}&tipo=${encodeURIComponent(tipo)}`),
    ]);

    if (!respApi.ok) {
      throw new Error("Erro ao consultar a API em Go (/api/mapa).");
    }

    const payload = await respApi.json();
    const porCodigo = new Map(payload.itens.map((item) => [item.codigo_ibge, item]));
    preencherBusca(payload.itens);

    if (geoLayer) {
      geoLayer.remove();
    }
    layersPorCodigo = new Map();

    geoLayer = L.geoJSON(malha, {
      style: (feature) => {
        const cod = String(feature.properties?.codarea ?? "");
        const registro = porCodigo.get(cod);
        return {
          fillColor: corPorValor(registro),
          weight: 0.6,
          color: "#ffffff",
          fillOpacity: 0.85,
        };
      },
      onEachFeature: (feature, layer) => {
        const cod = String(feature.properties?.codarea ?? "");
        layersPorCodigo.set(cod, layer);
        const registro = porCodigo.get(cod);
        const label = registro
          ? `${registro.nome} — ${registro.valor_absoluto ?? "sem dados"}`
          : `IBGE ${cod}`;
        layer.bindTooltip(label);
        layer.on("click", () => carregarDetalhesMunicipio(cod));
      },
    }).addTo(map);

    map.fitBounds(geoLayer.getBounds(), { padding: [12, 12] });
    const comDados = payload.itens.filter((i) => i.valor_absoluto !== null).length;
    statusEl.textContent = `${payload.itens.length} municípios de MG carregados (${comDados} com dados em ${ano}).`;
  } catch (err) {
    statusEl.textContent = err.message;
  }
}

searchEl.addEventListener("change", () => {
  const cod = municipiosPorNome.get(searchEl.value.trim().toLowerCase());
  if (!cod) return;
  const layer = layersPorCodigo.get(cod);
  if (layer) {
    map.fitBounds(layer.getBounds(), { maxZoom: 10 });
  }
  carregarDetalhesMunicipio(cod);
});

tipoEl.addEventListener("change", atualizarMapa);
anoEl.addEventListener("change", atualizarMapa);

atualizarMapa();
