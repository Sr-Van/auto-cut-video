# Empacotamento Windows (`AutoCortesBR.exe`)

## Pré-requisitos
1. Python 3.11+ com dependências de desenvolvimento instaladas:
   ```powershell
   pip install -r requirements-dev.txt
   ```
2. `ffmpeg` e `ffprobe` disponíveis no `PATH` do Windows (ou empacotados ao lado do executável).

## Gerar o pacote standalone
Na raiz do repositório:
```powershell
pyinstaller --clean --noconfirm build/autocortes.spec
```

A saída será gerada em `dist/AutoCortesBR/AutoCortesBR.exe` já contendo:
- `assets/fonts/` (fontes embutidas das legendas virais)
- `core/models/` (modelos ONNX de detecção facial YuNet)

## Verificação pós-build
- Execute `dist\AutoCortesBR\AutoCortesBR.exe`.
- Configure sua chave de API direto em **Ajustes → Cortes & IA → Chaves de API (.env)**.
- Caso `ffmpeg`/`ffprobe` não estejam no `PATH`, o app exibirá um aviso claro na tela inicial.
