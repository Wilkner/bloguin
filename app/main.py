import os
import shutil
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Form, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image as PILImage
from PIL.ExifTags import TAGS, GPSTAGS
from supabase import create_client, Client

# ========================================================
# 1. INICIALIZAÇÃO DO APP E CONFIGURAÇÃO DE AMBIENTE
# ========================================================
app = FastAPI(title="Bloguin API — Premium")

# Permite que seu admin.html e index.html conversem com a API sem travar no navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔒 SEGURANÇA MÁXIMA: As chaves fixas sumiram daqui!
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("❌ ERRO CRÍTICO: Variáveis de ambiente SUPABASE_URL ou SUPABASE_KEY não configuradas!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ========================================================
# 2. FUNÇÃO AUXILIAR: EXTRAÇÃO DE METADADOS EXIF (Fica no topo!)
# ========================================================
def extrair_metadados_exif(arquivo_foto) -> dict:
    meta = {"camera": "Desconhecida", "lat": None, "lon": None}
    try:
        arquivo_foto.file.seek(0)
        img = PILImage.open(arquivo_foto.file)
        exif = img._getexif()
        if not exif:
            return meta
        
        info_exif = {}
        for tag, valor in exif.items():
            decoded = TAGS.get(tag, tag)
            info_exif[decoded] = valor
            
        if "Make" in info_exif or "Model" in info_exif:
            fabricante = info_exif.get('Make', '').strip()
            modelo = info_exif.get('Model', '').strip()
            meta["camera"] = f"{fabricante} {modelo}".strip() or "Desconhecida"
            
        if "GPSInfo" in info_exif:
            gps_info = {}
            for key in info_exif["GPSInfo"].keys():
                decode_gps = GPSTAGS.get(key, key)
                gps_info[decode_gps] = info_exif["GPSInfo"][key]
            if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
                def to_decimal(ref, degree_tuple):
                    d = float(degree_tuple[0])
                    m = float(degree_tuple[1])
                    s = float(degree_tuple[2])
                    calc = d + (m / 60.0) + (s / 3600.0)
                    return -calc if ref in ['S', 'W'] else calc
                meta["lat"] = round(to_decimal(gps_info.get("GPSLatitudeRef", "N"), gps_info["GPSLatitude"]), 4)
                meta["lon"] = round(to_decimal(gps_info.get("GPSLongitudeRef", "E"), gps_info["GPSLongitude"]), 4)
    except Exception as e:
        print(f"⚠️ Aviso ao ler EXIF da imagem: {e}")
    finally:
        arquivo_foto.file.seek(0) # Sempre reseta o ponteiro para o arquivo ser salvo na sequência
    return meta


# ========================================================
# 3. ROTA DE PUBLICAÇÃO DE CRÔNICAS (Chama a função acima)
# ========================================================
@app.post("/api/v1/admin/publicar")
async def publicar_cronica(
    id_cronica: str = Form(...),
    titulo: str = Form(...),
    destino: str = Form(...),
    cidade: str = Form(...),
    data_viagem: str = Form(...),
    legenda: str = Form(...),
    texto: str = Form(...),
    foto: List[UploadFile] = File(...),
    video: Optional[UploadFile] = File(None),
    ia_texto: Optional[str] = Form(None),
    ia_video: Optional[str] = Form(None),
    ia_stories: Optional[str] = Form(None)
):
    try:
        # Conversão limpa para booleanos reais do Python
        bool_ia_texto = True if ia_texto == "true" else False
        bool_ia_video = True if ia_video == "true" else False
        bool_ia_stories = True if ia_stories == "true" else False

        # Montagem do rótulo amigável em string para a vitrine
        tags_ia = []
        if bool_ia_texto: tags_ia.append("Texto")
        if bool_ia_video: tags_ia.append("Vídeo")
        if bool_ia_stories: tags_ia.append("Stories")
        string_ia_fm = ", ".join(tags_ia) if tags_ia else "Nenhum"

        print(f"=== RECEBENDO NOVA CRÔNICA: {titulo} ===")
        print(f"Flags IA ativas: {string_ia_fm}")

        # Extração de metadados reais da primeira foto enviada
        metadados = extrair_metadados_exif(foto[0])

        # Salvamento físico das imagens com caminhos relativos
        caminhos_fotos = []
        for i, arquivo_foto in enumerate(foto):
            foto_ext = os.path.splitext(arquivo_foto.filename)[1] or ".jpg"
            sufixo = f"_{i+1}" if len(foto) > 1 else ""
            rel_path = f"assets/images/{id_cronica}{sufixo}{foto_ext}"
            
            with open(rel_path, "wb") as buffer:
                shutil.copyfileobj(arquivo_foto.file, buffer)
            caminhos_fotos.append(rel_path)

        string_fotos_fm = ", ".join(caminhos_fotos)
        string_legendas_fm = ", ".join([l.strip() for l in legenda.split(";")])

        # Salvamento físico do vídeo se houver
        video_path_str = ""
        if video and hasattr(video, 'filename') and video.filename:
            # Caso ainda queira enviar arquivos menores que 50mb localmente
            video_ext = os.path.splitext(video.filename)[1] or ".mp4"
            video_path_str = f"assets/videos/{id_cronica}{video_ext}"
            # Como colocamos a pasta assets/videos/ no .gitignore, ela roda local mas não vai pro Git
            with open(video_path_str, "wb") as buffer:
                shutil.copyfileobj(video.file, buffer)

        # Geração limpa do arquivo .txt com o Front Matter estruturado
        txt_destino = f"cronicas/{id_cronica}.txt"
        conteudo_txt = f"""---
title: {titulo}
destino: {destino}
cidade: {cidade}
data_viagem: {data_viagem}
ia_texto: {bool_ia_texto}
ia_video: {bool_ia_video}
ia_stories: {bool_ia_stories}
image: {string_fotos_fm}
video: {video_path_str}
legenda: {string_legendas_fm}
camera: {metadados['camera']}
latitude: {metadados['lat'] or 'Indisponível'}
longitude: {metadados['lon'] or 'Indisponível'}
---

{texto}
"""
        with open(txt_destino, "w", encoding="utf-8") as f:
            f.write(conteudo_txt)

        # Sincronização direta e atômica com o Supabase
        dados_banco = {
            "id": id_cronica,
            "titulo": titulo,
            "destino": destino,
            "cidade": cidade,
            "data_viagem": data_viagem,
            "rotulo_ia": string_ia_fm,
            "ia_texto": bool_ia_texto,
            "ia_video": bool_ia_video,
            "ia_stories": bool_ia_stories,
            "arquivo_path": txt_destino,
            "capa_url": caminhos_fotos[0],
            "atualizado_em": datetime.utcnow().isoformat()
        }

        print("Tentando sincronizar com o Supabase...")
        supabase.table("cronicas").upsert(dados_banco).execute()
        print("Sincronização concluída com sucesso!")

        return {
            "status": "sucesso",
            "mensagem": f"Crônica '{titulo}' integrada com selos de Content Credentials!"
        }

    except Exception as e:
        print(f"❌ ERRO CRÍTICO NA ROTA: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))