import yt_dlp

OUTPUT_DIR = '../temp'

def download_video(url: str, diretorio_saida: str = OUTPUT_DIR) -> str:

    ydl_opts = {
        'format': 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best',
        'paths': {
            'home': diretorio_saida,
            'temp': diretorio_saida
        },
        'outtmpl': diretorio_saida + '/%(title)s.%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Extraindo informações e baixando: {url}...")
            info_dict = ydl.extract_info(url, download=True)
            
            caminho_arquivo = ydl.prepare_filename(info_dict)
            
            caminho_arquivo = caminho_arquivo.rsplit('.', 1)[0] + '.mp4'
            print("caminho definido do arquivo: ", caminho_arquivo)
            return caminho_arquivo
            
    except Exception as e:
        print(f"Erro ao baixar o vídeo: {e}")
        return None
