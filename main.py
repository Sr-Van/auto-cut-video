import core.config as config


def main():
    print("API_KEY:", "carregada" if config.API_KEY else "vazia")
    print("MODELO_GEMINI:", config.MODELO_GEMINI)
    print("WHISPER_MODEL:", config.WHISPER_MODEL)
    print("TEMPERATURA:", config.TEMPERATURA)
    print("PADDING_S:", config.PADDING_S)
    print("LANGUAGE:", config.LANGUAGE)
    print("OUTPUT_DIR:", config.OUTPUT_DIR)


if __name__ == "__main__":
    main()
