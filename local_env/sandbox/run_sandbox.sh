#!/bin/bash

CONTAINER_NAME="kaggle-workspace"
IMAGE_NAME="vertex-kaggle-sandbox:latest"

echo "[*] Limpiando contenedores anteriores si existen..."
docker rm -f $CONTAINER_NAME 2>/dev/null || true

echo "[*] Levantando el sandbox persistente en segundo plano..."
docker run -d \
    --name $CONTAINER_NAME \
    --restart always \
    -v "$(pwd)/../../data/raw/snapshots:/workspace" \
    $IMAGE_NAME

echo "[+] Sandbox '$CONTAINER_NAME' activo y blindado."