# Ollama systemd override — генерируется из setup.sh через envsubst
# Шаблон: deploy/ollama-override.conf.tpl

[Service]
Environment="OLLAMA_MODELS=${OLLAMA_MODELS_PATH}"
Environment="OLLAMA_FLASH_ATTENTION=${OLLAMA_FLASH_ATTENTION}"
Environment="OLLAMA_KEEP_ALIVE=${OLLAMA_KEEP_ALIVE}"
Environment="OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
Environment="OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"
Environment="CUDA_VISIBLE_DEVICES=0"
