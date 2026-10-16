ARG BASE_IMAGE=pytorch/pytorch:2.7.1-cuda12.6-cudnn9-runtime
FROM ${BASE_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ARG APT_MIRROR=

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PIP_DEFAULT_TIMEOUT=120 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/src \
    TOKENIZERS_PARALLELISM=false

RUN if [ -n "${APT_MIRROR}" ]; then \
      sed -i "s|http://archive.ubuntu.com/ubuntu|${APT_MIRROR}|g; s|http://security.ubuntu.com/ubuntu|${APT_MIRROR}|g" /etc/apt/sources.list; \
    fi && \
    apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update && \
    apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      libreoffice-writer \
      sudo \
      tesseract-ocr \
      tesseract-ocr-chi-sim \
      tesseract-ocr-eng \
      vim && \
    rm -rf /var/lib/apt/lists/*

COPY docker/requirements.txt /tmp/requirements.txt

# PyTorch is supplied by the official image; never replace its CUDA build.
RUN python -m pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r /tmp/requirements.txt \
    && python -m pip check \
    && python -m pip freeze > /opt/environment-lock.txt \
    && rm -f /tmp/requirements.txt

WORKDIR /workspace
CMD ["bash", "-lc", "sleep infinity"]
