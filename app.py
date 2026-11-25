"""
EPDK Şarj Hizmeti Piyasası Analitik Platformu — Otomatik Veri Toplama MVP
Streamlit & Plotly tabanlı gösterge paneli

Dashboard açıldığında:
1. Mevcut güncel anlık görüntü varsa otomatik yükler.
2. Güncel veri yoksa canlı EPDK API'sinden otomatik toplar.
3. Kullanıcı etkileşimi gerektirmez (dosya yükleme / arşiv seçimi yok).
4. Filtre değişiklikleri yeniden API isteği tetiklemez (oturum önbelleği).
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import os
import io
import hashlib
import gzip

from src.data_loader import (
    load_dataset,
    generate_synthetic_fixture,
    COLUMN_ALIASES
)
from src.validator import validate_charging_dataset
from src.dashboard_controller import filter_dataset, verify_snapshot_integrity, handle_file_upload
from src.metrics import (
    compute_kpis,
    get_ac_dc_distribution,
    get_operator_socket_ranking,
    get_operator_power_ranking,
    get_observed_power_distribution
)
from src.auto_collector import (
    run_auto_collection,
    load_snapshot_from_manifest,
    get_local_data_dir,
    format_timestamp_istanbul,
    parse_manifest_timestamp,
    is_snapshot_fresh,
    AutoCollectionResult,
)

# ------------------------------------------------------------------------------
# Sayfa Yapılandırması
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="EPDK Şarj Piyasası Analitiği",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Özel CSS ile kurumsal ve net görünüm
st.markdown("""
<style>
    .kpi-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 14px 16px;
        border-left: 4px solid #1f77b4;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .kpi-title {
        font-size: 0.82rem;
        color: #6c757d;
        margin-bottom: 4px;
        font-weight: 600;
        text-transform: uppercase;
    }
    .kpi-value {
        font-size: 1.7rem;
        font-weight: 700;
        color: #212529;
    }
    .kpi-sub {
        font-size: 0.73rem;
        color: #888;
        margin-top: 4px;
    }
    .freshness-badge {
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .fresh { background-color: #d4edda; color: #155724; }
    .stale { background-color: #fff3cd; color: #856404; }
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# Başlık ve Bilgilendirme
# ------------------------------------------------------------------------------
st.title("⚡ Türkiye Elektrikli Araç Şarj Altyapısı Analitiği")
st.caption("EPDK Şarj İstasyonları & Soket Dağılımı — Otomatik Veri Toplama MVP")

# Metodolojik ve Hukuki Uyarı Notu
with st.expander("ℹ️ Metodoloji, Veri Sınırları ve Önemli Açıklamalar", expanded=False):
    st.markdown("""
    - **Varlık Ayrımı:** Bu analizde **İstasyon** (fiziksel şarj tesisi/lokasyon) ve **Soket** (bağımsız şarj konnektörü) kesin olarak ayrıştırılmıştır. Bir istasyonda birden fazla soket bulunabilir. Bazı istasyonlar lisanslı olmakla birlikte anlık görüntüde henüz soket içermeyebilir (soketsiz istasyon).
    - **Soket Sayısı Payı:** Operatör yüzdeleri, seçilen anlık görüntü veya filtre kapsamındaki **toplam soket sayısı içindeki payı** ifade eder; ciro, kullanım oranı veya enerji piyasası payını temsil etmez.
    - **Kurulu Güç ve Birim Uyarısı:** Kaynak API yanıtında ve dışa aktarım tablolarında güç birimi açıkça belirtilmemiştir. Sektör standardı gereği değerlerin **kW (kilowatt)** olduğu kabul edilmiştir; bu kabul doğrulanmamış bir yorumdur. Raporda hesaplanan toplam güç, soketlerin bireysel anma güçlerinin aritmetik toplamı olup, istasyonun eşzamanlı **şebeke bağlantı kapasitesini temsil etmez**.
    - **Zaman Boyutu:** Tek bir anlık görüntü (*snapshot*), veri çekilme anındaki durumu yansıtır. Tarihsel kanıt olmaksızın tek bir anlık görüntüden aylık yeni kurulum eğilimleri çıkarılamaz.
    - **Veri Hakları:** EPDK verileri ticari olmayan araştırma ve analiz amacıyla yerel olarak işlenir; ham veriler genel erişime açılmaz.
    """)


# ------------------------------------------------------------------------------
# Otomatik Veri Toplama Mantığı
# ------------------------------------------------------------------------------
local_data_dir = get_local_data_dir()

raw_df = None
applied_mappings = {}
is_synthetic = False
snapshot_meta = {}
active_source_label = "Bilinmiyor"
upload_error_msg = None

# Session state keys
_SNAP_KEY = "epdk_snapshot_data"
_META_KEY = "epdk_snapshot_meta"
_MANIFEST_KEY = "epdk_manifest"
_SOURCE_KEY = "epdk_source_label"
_FORCE_KEY = "epdk_force_refresh"

# Check dev mode toggle
dev_mode = st.sidebar.checkbox("🛠️ Geliştirici Modu", value=False, help="Dosya yükleme, arşiv seçimi ve sentetik veri seçeneklerini gösterir.")

# Manual refresh button in sidebar
st.sidebar.markdown("---")
st.sidebar.header("📡 Veri Durumu")

if st.sidebar.button("🔄 Şimdi Güncelle", help="EPDK API'sinden güncel veri toplar"):
    # Clear cached data to force re-collection and re-validation
    keys_to_clear = [k for k in list(st.session_state.keys()) if k in [_SNAP_KEY, _META_KEY, _MANIFEST_KEY, _SOURCE_KEY] or k.startswith("_validated_df_") or k.startswith("_validation_summary_")]
    for key in keys_to_clear:
        del st.session_state[key]
    st.session_state[_FORCE_KEY] = True

# Dev-mode data source selection
if dev_mode:
    with st.sidebar.expander("🛠️ Geliştirici Veri Kaynakları", expanded=False):
        dev_source = st.radio(
            "Veri Kaynağı:",
            options=["Otomatik (EPDK API)", "Yerel Dosya Yükle", "Yerel Arşiv Seç", "Sentetik Test Verisi"],
            index=0,
            key="dev_source_radio"
        )

        if dev_source == "Yerel Dosya Yükle":
            uploaded_file = st.file_uploader(
                "Dosya Yükleyin (CSV / JSON / ZIP):",
                type=["csv", "json", "zip", "gz"],
            )
            if uploaded_file is not None:
                raw_df, applied_mappings, upload_error_msg = handle_file_upload(uploaded_file, load_dataset)
                if raw_df is not None:
                    snapshot_meta = raw_df.attrs.get("metadata", {})
                    active_source_label = f"Yüklenen Dosya: {uploaded_file.name}"
                    st.success(f"Yüklendi: {uploaded_file.name} ({len(raw_df):,} kayıt)")

        elif dev_source == "Yerel Arşiv Seç":
            local_files = []
            if local_data_dir.exists():
                local_files = [
                    f for f in local_data_dir.glob("*")
                    if f.suffix.lower() in [".json", ".zip", ".csv", ".gz"]
                    and not f.name.endswith(".jsonl")
                    and "konumlu" not in f.name.lower()
                    and "conflict" not in f.name.lower()
                    and not f.name.startswith("epdk_meta_")
                ]
                local_files.sort(key=lambda x: (0 if "raw" in x.name else 1 if "istasyonlar" in x.name else 2, x.name))

            if local_files:
                selected_local = st.selectbox(
                    "Yerel Arşivden Dosya Seçin:",
                    options=[f.name for f in local_files],
                    index=0
                )
                if selected_local:
                    target_path = local_data_dir / selected_local
                    try:
                        raw_df, applied_mappings = load_dataset(target_path, filename_hint=selected_local)
                        snapshot_meta = raw_df.attrs.get("metadata", {})
                        active_source_label = f"Yerel Arşiv: {selected_local}"
                        st.success(f"Yüklendi: {selected_local} ({len(raw_df):,} satır)")
                    except Exception as e:
                        raw_df = None
                        st.error(f"Dosya okuma hatası: {e}")
            else:
                st.info("_local_data klasöründe uygun dosya bulunamadı.")

        elif dev_source == "Sentetik Test Verisi":
            is_synthetic = True
            active_source_label = "Sentetik Test Verisi"
            raw_df = generate_synthetic_fixture(num_records=250, seed=42)
            applied_mappings = {col: col for col in raw_df.columns}
            st.info("🧪 Sentetik test verisi kullanılıyor.")

        # If dev mode selected a non-auto source and loaded data, skip auto-collection
        if dev_source != "Otomatik (EPDK API)" and (raw_df is not None or is_synthetic):
            # Data already loaded via dev mode, skip auto-collection below
            pass
        else:
            # Fall through to auto-collection
            dev_source = "Otomatik (EPDK API)"


# ------------------------------------------------------------------------------
# Otomatik Veri Toplama (Varsayılan Akış)
# ------------------------------------------------------------------------------
# Only run auto-collection if no data loaded yet (dev mode didn't provide data)
if raw_df is None and not is_synthetic and upload_error_msg is None:
    # Check session-state cache first
    if _SNAP_KEY in st.session_state and not st.session_state.get(_FORCE_KEY, False):
        raw_df = st.session_state[_SNAP_KEY]
        snapshot_meta = st.session_state.get(_META_KEY, {})
        active_source_label = st.session_state.get(_SOURCE_KEY, "Önbellek")
        applied_mappings = {}  # Already normalized
    else:
        # Clear force flag
        if _FORCE_KEY in st.session_state:
            del st.session_state[_FORCE_KEY]

        force_refresh = st.session_state.pop(_FORCE_KEY, False) if _FORCE_KEY in st.session_state else False

        with st.spinner("📡 EPDK verileri yükleniyor..."):
            result = run_auto_collection(
                data_dir=local_data_dir,
                force_refresh=force_refresh,
            )

        if result.success and result.manifest:
            # Load the actual data from the snapshot file
            df_loaded, load_error = load_snapshot_from_manifest(result.manifest, local_data_dir)
            if df_loaded is not None:
                raw_df = df_loaded
                snapshot_meta = result.manifest
                applied_mappings = {}

                # Determine source label
                ts = parse_manifest_timestamp(result.manifest)
                ts_display = format_timestamp_istanbul(ts) if ts else "Bilinmiyor"
                station_count = result.manifest.get("station_count", "?")
                socket_count = result.manifest.get("socket_count", "?")

                if result.source == "fresh_collection":
                    active_source_label = f"EPDK API — Canlı Toplama ({ts_display})"
                    st.sidebar.success(f"✅ Güncel veri toplandı: {station_count:,} istasyon, {socket_count:,} soket")
                elif result.source == "existing_snapshot":
                    active_source_label = f"EPDK Anlık Görüntü ({ts_display})"
                    if result.is_stale:
                        st.sidebar.warning(f"⚠️ Eski anlık görüntü kullanılıyor ({ts_display})")
                    else:
                        st.sidebar.success(f"✅ Güncel veri: {station_count:,} istasyon ({ts_display})")

                # Cache in session state
                st.session_state[_SNAP_KEY] = raw_df
                st.session_state[_META_KEY] = snapshot_meta
                st.session_state[_SOURCE_KEY] = active_source_label
                st.session_state[_MANIFEST_KEY] = result.manifest
            else:
                st.error(f"⚠️ Anlık görüntü dosyası yüklenemedi: {load_error}")
                if result.error_message:
                    st.error(result.error_message)
                st.info("💡 'Şimdi Güncelle' butonuna basarak tekrar deneyin veya Geliştirici Modunda dosya yükleyin.")
                st.stop()
        else:
            # No data available at all
            if result.is_stale and result.manifest:
                # Stale data with error
                df_loaded, load_error = load_snapshot_from_manifest(result.manifest, local_data_dir)
                if df_loaded is not None:
                    raw_df = df_loaded
                    snapshot_meta = result.manifest
                    ts = parse_manifest_timestamp(result.manifest)
                    ts_display = format_timestamp_istanbul(ts) if ts else "Bilinmiyor"
                    active_source_label = f"EPDK Anlık Görüntü ({ts_display}) — Eski"
                    st.sidebar.warning(f"⚠️ Bağlantı hatası: Eski veri gösteriliyor ({ts_display})")
                    if result.error_message:
                        st.sidebar.error(f"Hata: {result.error_message}")
                    st.session_state[_SNAP_KEY] = raw_df
                    st.session_state[_META_KEY] = snapshot_meta
                    st.session_state[_SOURCE_KEY] = active_source_label
                else:
                    st.error(f"🔌 EPDK verisi alınamadı: {result.error_message or 'Bilinmeyen hata'}")
                    st.info("💡 İnternet bağlantınızı kontrol edin ve 'Şimdi Güncelle' butonuna basın.")
                    st.stop()
            else:
                st.error(f"🔌 EPDK verisi alınamadı: {result.error_message or 'Mevcut veri bulunamadı.'}")
                st.info("💡 İnternet bağlantınızı kontrol edin ve 'Şimdi Güncelle' butonuna basın.\n\nGeliştirici Modunu açarak yerel dosya yükleyebilir veya sentetik test verisi kullanabilirsiniz.")
                st.stop()


# ------------------------------------------------------------------------------
# Veri Yoksa: Boş Durum (Empty State)
# ------------------------------------------------------------------------------
if upload_error_msg:
    st.error(f"⚠️ Yüklenen dosya işlenemedi: {upload_error_msg}. Lütfen geçerli bir JSON, CSV veya ZIP dosyası seçin.")
    st.stop()

if raw_df is None or raw_df.empty:
    st.info("📡 Veri yüklenemedi. 'Şimdi Güncelle' butonuna basın veya Geliştirici Modunda dosya yükleyin.")
    st.stop()

# Check dataset integrity from loader
if raw_df.attrs.get("metadata", {}).get("integrity_error"):
    st.error(f"🚨 Veri Bütünlüğü Hatası: {raw_df.attrs['metadata']['integrity_error']}")
    st.stop()


# ------------------------------------------------------------------------------
# Veri Doğrulama ve Kalite Kontrolü (Önbellekli)
# ------------------------------------------------------------------------------
VALIDATION_VERSION = "v1.2.2"
snap_ident = snapshot_meta.get("snapshot_id") or snapshot_meta.get("sha256_hash") or "default"
val_df_key = f"_validated_df_{snap_ident}_{VALIDATION_VERSION}"
val_sum_key = f"_validation_summary_{snap_ident}_{VALIDATION_VERSION}"

if val_df_key in st.session_state and val_sum_key in st.session_state:
    validated_df = st.session_state[val_df_key]
    summary = st.session_state[val_sum_key]
else:
    with st.spinner("⚡ Veri doğrulaması ve kalite kontrolleri yapılıyor..."):
        validated_df, summary = validate_charging_dataset(raw_df)
        st.session_state[val_df_key] = validated_df
        st.session_state[val_sum_key] = summary

# Metaveri ve Aktif Kaynak rozeti
meta_cols = st.columns([2, 1])
with meta_cols[0]:
    snap_ts = snapshot_meta.get("snapshot_timestamp") or snapshot_meta.get("timestamp_utc")
    if snap_ts:
        # Parse and display in Istanbul timezone
        ts_dt = parse_manifest_timestamp(snapshot_meta)
        if ts_dt:
            ts_display = format_timestamp_istanbul(ts_dt)
            freshness = is_snapshot_fresh(snapshot_meta)
            badge_class = "fresh" if freshness else "stale"
            badge_text = "Güncel" if freshness else "Eski"
            st.markdown(
                f'🕒 **Son Güncelleme:** `{ts_display}` (Europe/Istanbul) '
                f'<span class="freshness-badge {badge_class}">{badge_text}</span>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(f"🕒 **Kaynak Anlık Görüntü Zamanı:** `{snap_ts}`")
    else:
        st.markdown(f"📍 **Aktif Veri:** `{active_source_label}`")

    # Source label
    station_ct = snapshot_meta.get("station_count")
    socket_ct = snapshot_meta.get("socket_count")
    if station_ct and socket_ct:
        st.caption(f"📊 Kaynak: EPDK API Gateway — {station_ct:,} istasyon, {socket_ct:,} soket")

with meta_cols[1]:
    h = snapshot_meta.get("sha256_hash") or snapshot_meta.get("content_hash")
    if h:
        st.caption(f"🔒 SHA-256: `{h[:12]}...`")

has_sockets = snapshot_meta.get("has_socket_data", True) and summary.unique_sockets > 0
if not has_sockets:
    st.warning("⚠️ **Soket verisi mevcut değil:** Yalnızca istasyon sicil tablosu yüklendi. Soket metrikleri ve güç analizi için eşleşen soketler CSV dosyası gereklidir.")

if is_synthetic:
    st.warning("⚠️ **DİKKAT:** Şu anda görüntülenen veriler **SENTETİK TEST VERİSİDİR**. Gerçek EPDK piyasa istatistiklerini yansıtmaz.")

# Doğrulama Kalite Özeti Rozetleri
col_v1, col_v2, col_v3, col_v4 = st.columns(4)
with col_v1:
    st.metric("Kayıtlı İstasyon Sayısı", f"{summary.unique_stations:,}", help="EPDK sicilinde kayıtlı tüm istasyonlar")
with col_v2:
    st.metric("Soketi Bulunan İstasyon", f"{summary.stations_with_sockets:,}", delta=f"{summary.stations_without_sockets} soketsiz" if summary.stations_without_sockets > 0 else None, delta_color="inverse")
with col_v3:
    if has_sockets:
        st.metric("Benzersiz Soket Sayısı", f"{summary.unique_sockets:,}", help="Ağdaki tüm tekil şarj soketleri")
    else:
        st.metric("Benzersiz Soket Sayısı", "Mevcut Değil", help="Soket tablosu eksik")
with col_v4:
    if summary.conflicting_ac_dc_count > 0:
        st.metric("Çelişkili Sınıflandırma", f"{summary.conflicting_ac_dc_count} soket", delta="AC/DC Çelişkisi", delta_color="inverse", help="Örn: soketTipi=DC iken soketTuru=AC_TYPE2")
    else:
        st.metric("Soket ID Tekilliği", "%100 Benzersiz")

# ------------------------------------------------------------------------------
# Filtreleme Bölümü (Sidebar)
# ------------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.header("🔍 Dinamik Filtreler")

# Operatör Filtresi
available_operators = sorted(validated_df["operator_name"].dropna().unique().tolist())
operator_counts = validated_df["operator_name"].value_counts()
top_operators = operator_counts.head(10).index.tolist()

filter_all_ops = st.sidebar.checkbox("Tüm Operatörleri Seç", value=True)
if filter_all_ops:
    selected_operators = available_operators
else:
    selected_operators = st.sidebar.multiselect(
        "Operatör Seçimi:",
        options=available_operators,
        default=top_operators[:5]
    )

# Akım Tipi Filtresi
selected_type = st.sidebar.radio(
    "Akım Türü (AC/DC):",
    options=["Tümü", "AC", "DC"],
    index=0
)

# Güç Aralığı Filtresi
valid_powers = validated_df["power_kw_normalized"].dropna() if "power_kw_normalized" in validated_df.columns else pd.Series(dtype=float)
min_power = float(valid_powers.min()) if not valid_powers.empty else 0.0
max_power = float(valid_powers.max()) if not valid_powers.empty else 500.0

if min_power < max_power:
    power_range = st.sidebar.slider(
        "Güç Aralığı (kW*):",
        min_value=float(min_power),
        max_value=float(max_power),
        value=(float(min_power), float(max_power)),
        step=1.0
    )
else:
    power_range = (min_power, max_power)

# Filtreleri Uygula
filtered_df, is_socket_filter_active, station_subtext = filter_dataset(
    validated_df=validated_df,
    filter_all_ops=filter_all_ops,
    selected_operators=selected_operators,
    selected_type=selected_type,
    power_range=power_range,
    min_power=min_power,
    max_power=max_power,
)

# ------------------------------------------------------------------------------
# Temel KPI Kartları
# ------------------------------------------------------------------------------
kpis = compute_kpis(filtered_df)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Benzersiz İstasyon</div>
        <div class="kpi-value">{kpis['unique_stations']:,}</div>
        <div class="kpi-sub">{station_subtext}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    val_str = f"{kpis['unique_sockets']:,}" if kpis['unique_sockets'] is not None else "Mevcut Değil"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Benzersiz Soket</div>
        <div class="kpi-value">{val_str}</div>
        <div class="kpi-sub">Kayıtlı Şarj Soketleri</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    sps_str = f"{kpis['sockets_per_station']}" if kpis['sockets_per_station'] is not None else "-"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Soket / İstasyon</div>
        <div class="kpi-value">{sps_str}</div>
        <div class="kpi-sub">Ortalama Soket Yoğunluğu</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    conf_count = kpis.get('conflicting_type_sockets_count', 0) or 0
    if kpis['ac_socket_count'] is not None and kpis['dc_socket_count'] is not None:
        if conf_count > 0:
            ac_dc_str = f"{kpis['ac_socket_count']:,} / {kpis['dc_socket_count']:,} / {conf_count:,}"
            ac_dc_sub = "AC / DC / Çelişkili Soket"
        else:
            ac_dc_str = f"{kpis['ac_socket_count']:,} / {kpis['dc_socket_count']:,}"
            ac_dc_sub = "AC Soket / DC Soket"
    else:
        ac_dc_str = "-"
        ac_dc_sub = "Veri Yok"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">AC / DC Dağılımı</div>
        <div class="kpi-value">{ac_dc_str}</div>
        <div class="kpi-sub">{ac_dc_sub}</div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    if kpis['total_socket_power_kw'] is not None:
        pwr_str = f"{kpis['total_socket_power_kw']:,.1f} <span style='font-size:0.9rem;'>kW*</span>"
    else:
        pwr_str = "-"
    st.markdown(f"""
    <div class="kpi-card" style="border-left-color: #ff7f0e;">
        <div class="kpi-title">Toplam Soket Güç Değeri</div>
        <div class="kpi-value">{pwr_str}</div>
        <div class="kpi-sub">*Kaynak birimi doğrulanmadı (Sektör kabulü kW)</div>
    </div>
    """, unsafe_allow_html=True)

st.caption("*Not: Güç birimi (kW) kaynak API yanıtında açıkça belirtilmemiş olup doğrulanmamış sektör kabulüdür. Toplam soket güç değeri, soket anma güçlerinin aritmetik toplamı olup şebeke eşzamanlı bağlantı kapasitesini temsil etmez. Türü çelişkili soketlerin doğrulanmış anma güçleri genel toplama dahil edilmiş; AC/DC güç dağılımında ise 'Çelişkili' kategorisinde gösterilmiştir.")
st.markdown("<br>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# Grafikler Bölümü (Plotly)
# ------------------------------------------------------------------------------
if filtered_df.empty:
    st.warning("⚠️ Seçilen filtre kriterlerine uygun herhangi bir kayıt bulunamadı.")
else:
    tab1, tab2, tab3 = st.tabs(["📊 Pazar & Operatör Dağılımı", "⚡ Güç Dağılımı (kW*)", "📋 Veri Tablosu ve Kalite Raporu"])

    with tab1:
        g_col1, g_col2 = st.columns([1, 2])
        
        with g_col1:
            st.subheader("AC / DC Soket Dağılımı")
            ac_dc_df = get_ac_dc_distribution(filtered_df)
            if not ac_dc_df.empty and ac_dc_df["Soket Sayısı"].sum() > 0:
                fig_pie = px.pie(
                    ac_dc_df,
                    values="Soket Sayısı",
                    names="Tip",
                    hole=0.45,
                    color="Tip",
                    color_discrete_map={"AC": "#1f77b4", "DC": "#ff7f0e", "Çelişkili": "#d62728", "Bilinmiyor": "#7f7f7f"}
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+value')
                fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
                st.plotly_chart(fig_pie, use_container_width=True)
                st.caption("Yüzde paydası: Filtre kapsamındaki toplam benzersiz soket sayısı.")
            else:
                st.info("Soket verisi mevcut değil.")

        with g_col2:
            st.subheader("Lider Operatörler (Soket Sayısı Payı)")
            op_ranking = get_operator_socket_ranking(filtered_df, top_n=12)
            if not op_ranking.empty and op_ranking["Soket Sayısı"].sum() > 0:
                fig_op = px.bar(
                    op_ranking,
                    x="Soket Sayısı",
                    y="Operatör",
                    orientation="h",
                    text="Soket Sayısı",
                    color="Soket Sayısı",
                    color_continuous_scale="Blues"
                )
                fig_op.update_layout(
                    yaxis=dict(autorange="reversed"),
                    margin=dict(t=10, b=10, l=10, r=10),
                    coloraxis_showscale=False
                )
                st.plotly_chart(fig_op, use_container_width=True)
                st.caption("Not: Soket Sayısı Payı (%), seçilen kapsamdaki toplam soket sayısına oranlanmıştır; enerji tüketim veya ciro payını ifade etmez.")
            else:
                st.info("Operatör soket verisi bulunamadı.")

    with tab2:
        p_col1, p_col2 = st.columns(2)
        
        with p_col1:
            st.subheader("Gözlemlenen Soket Güçleri Dağılımı (kW*)")
            power_dist = get_observed_power_distribution(filtered_df)
            if not power_dist.empty and power_dist["Soket Sayısı"].sum() > 0:
                fig_p = px.bar(
                    power_dist,
                    x="Güç (kW)",
                    y="Soket Sayısı",
                    color="Akım Tipi",
                    barmode="stack",
                    color_discrete_map={"AC": "#1f77b4", "DC": "#ff7f0e", "Çelişkili": "#d62728", "Bilinmiyor": "#7f7f7f"}
                )
                fig_p.update_layout(
                    xaxis_title="Anma Gücü (kW*)",
                    yaxis_title="Soket Sayısı",
                    margin=dict(t=10, b=10, l=10, r=10)
                )
                st.plotly_chart(fig_p, use_container_width=True)
            else:
                st.info("Güç dağılımı verisi bulunamadı.")
                
        with p_col2:
            st.subheader("Operatör Kurulu Soket Güçleri (Toplam kW*)")
            op_power = get_operator_power_ranking(filtered_df, top_n=12)
            if not op_power.empty and op_power["Toplam Soket Gücü (kW)"].sum() > 0:
                fig_opp = px.bar(
                    op_power,
                    x="Toplam Soket Gücü (kW)",
                    y="Operatör",
                    orientation="h",
                    text="Toplam Soket Gücü (kW)",
                    color="Toplam Soket Gücü (kW)",
                    color_continuous_scale="Oranges"
                )
                fig_opp.update_layout(
                    yaxis=dict(autorange="reversed"),
                    margin=dict(t=10, b=10, l=10, r=10),
                    coloraxis_showscale=False
                )
                st.plotly_chart(fig_opp, use_container_width=True)
            else:
                st.info("Operatör güç verisi bulunamadı.")

    with tab3:
        st.subheader("Filtrelenmiş Kayıtlar ve Doğrulama Durumu")
        display_cols = [
            c for c in ["station_id", "station_name", "socket_id", "operator_name", "socket_type_normalized", "power_kw_normalized", "_is_valid", "_validation_errors"]
            if c in filtered_df.columns
        ]
        st.dataframe(filtered_df[display_cols].head(200), use_container_width=True)
        st.caption("Performans ve kullanıcı deneyimi için ilk 200 satır listelenmektedir.")
