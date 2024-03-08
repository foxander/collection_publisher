#
# This file is part of collector.
# Copyright (C) 2024 INPE.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/gpl-3.0.html>.
#

ARG BASE_IMAGE=python:3.9-slim
ARG GIT_COMMIT

FROM ${BASE_IMAGE}

# Image metadata
LABEL "br.inpe.big.maintainer"="Big INPE"
LABEL "br.inpe.big.title"="Docker image for data publishing"
LABEL "br.inpe.big.description"="Docker image to publish Images scenes as collections."
LABEL "br.inpe.big.git_commit"="${GIT_COMMIT}"

ARG COLLECTION_PUBLISHER_APP_VERSION="0.1.0"
ARG COLLECTION_PUBLISHER_APP_USER_NAME="big"
ARG COLLECTION_PUBLISHER_APP_USER_ID=1000
ARG COLLECTION_PUBLISHER_APP_USER_GROUP="big"
ARG COLLECTION_PUBLISHER_APP_USER_GROUP_ID=1000

RUN apt-get update && \
    apt-get install --yes nano python3-pip git pkg-config cmake libtool autoconf libgdal-dev && \
    pip3 install pip --upgrade && \
    rm -rf /var/lib/apt/lists/*

ADD --chown=${COLLECTION_PUBLISHER_APP_USER_ID}:${COLLECTION_PUBLISHER_APP_USER_GROUP} \
    . /opt/collection_publisher/${COLLECTION_PUBLISHER_APP_VERSION}/

WORKDIR /opt/collection_publisher/${COLLECTION_PUBLISHER_APP_VERSION}

RUN python3 -m pip install -U pip setuptools wheel && \
    python3 -m pip install -r requirements.txt && \
    python3 -m pip install pygdal=="`gdal-config --version`.*" && \
    python3 -m pip install .

RUN groupadd --gid ${COLLECTION_PUBLISHER_APP_USER_GROUP_ID} ${COLLECTION_PUBLISHER_APP_USER_GROUP} && \
    useradd --create-home \
            --shell /bin/bash \
            --uid ${COLLECTION_PUBLISHER_APP_USER_ID} \
            --gid ${COLLECTION_PUBLISHER_APP_USER_GROUP} ${COLLECTION_PUBLISHER_APP_USER_NAME}

USER ${COLLECTION_PUBLISHER_APP_USER_ID}:${COLLECTION_PUBLISHER_APP_USER_GROUP_ID}

CMD ["collection_publisher"]
