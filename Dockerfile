#
# PPaxe-app web service docker requires
#    + debian:jessie or ubuntu:16.04
#    + python 2.7
#    + flask
#    + stanford-corenlp
#
# Build this docker with:
#   docker build -t ppaxewui.docker -f=./Dockerfile_ppaxe_wui .
#
# Run this docker with:
#   docker run -d -ti --net=host \
#              --env PPAXE_EUSER="your.email.user" \
#              --env PPAXE_EPASSW="your.email.passwd" \
#              --env PPAXE_EMAIL="your.email.user@your.email.domain" \
#              ppaxewui.docker
#
#   the container works as a web service, thus results are retrieved as
#   web pages and downloadable links.
#
FROM ubuntu:16.04

MAINTAINER Josep F Abril, jabril@ub.edu
MAINTAINER Sergio Castillo-Lara, s.cast.lara@gmail.com

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y \
               build-essential \
               ca-certificates \
               gcc \
               git \
               libpq-dev \
               make \
               apt-utils \
               python-pip \
               python2.7 \
               python2.7-dev \
               sqlite3 \
               libsqlite3-dev \
               wget \
               ssh \
               unzip \
               openjdk-8-jdk \
    && apt-get autoremove \
    && apt-get clean

RUN pip install --upgrade pip
RUN pip install -U "pycorenlp==0.3.0"
RUN pip install -U "scipy==0.17.0"
RUN pip install -U "sklearn==0.0"
RUN pip install -U "requests==2.4.3"
RUN pip install -U "scikit-learn==0.18.2"
RUN pip install -U "matplotlib==2.0.2"
RUN pip install -U "networkx==2.2"
RUN pip install -U "pysqlite"
RUN pip install -U "uuid"

RUN wget https://nlp.stanford.edu/software/stanford-corenlp-full-2017-06-09.zip \
    && unzip stanford-corenlp-full-2017-06-09.zip \
    && wget https://compgen.bio.ub.edu/datasets/PPaxe_files/FINAL-ner-model.AImed%2BMedTag%2BBioInfer.ser.gz \
         -O /stanford-corenlp-full-2017-06-09/FINAL-ner-model.AImed+MedTag+BioInfer.ser.gz \
    && wget https://nlp.stanford.edu/software/stanford-english-corenlp-2017-06-09-models.jar \
         -O /stanford-corenlp-full-2017-06-09/stanford-english-corenlp-2017-06-09-models.jar 

RUN echo "# Installing ppaxe lib..." \
    && git --no-pager clone https://github.com/scastlara/ppaxe.git
#        # repo clone at https://github.com/CompGenLabUB/ppaxe.git
RUN sed -i 's%\.\./%/stanford-corenlp-full-2017-06-09/%' \
           /ppaxe/ppaxe/data/server.properties

WORKDIR /ppaxe

RUN wget https://compgen.bio.ub.edu/datasets/PPaxe_files/RF_scikit.pkl \
      -O ./ppaxe/data/RF_scikit.pkl \
    && pip install ./

#    
# installing web app

RUN pip install flask
RUN pip install xhtml2pdf
# RUN pip install -U "joblib==0.11"

# Ensuring the joblib is capable of running "loky" parallel mode
RUN mkdir -vp /ppaxe/install \
    && cd /ppaxe/install \
    && git clone git://github.com/joblib/joblib.git \
    && cd joblib && pip install .

WORKDIR /ppaxe
    
RUN echo "# Downloading and installing web-app... " \
    && git --no-pager clone https://github.com/scastlara/ppaxe-app.git
#        # repo clone at https://github.com/CompGenLabUB/ppaxe-app.git

RUN addgroup --gid 1000 www \
    && adduser --gid 1000 --uid 1000 \
               --shell /bin/bash \
               --no-create-home --system www \
    && mkdir -vp /ppaxe/logs \
                 /ppaxe/ppaxe-app/tmp

#    
# preparing script to launch container services

RUN \
  echo 'from ppaxeapp import app\n\
if __name__ == "__main__":\n\
    app.run()\n' \
  > /ppaxe/ppaxe-app/wsgi.py

# RUN cat /ppaxe/ppaxe-app/wsgi.py

##
## System params... set up your own \n\
##
ENV PPAXE_DEBUG=0
# ENV PPAXE_THREADS=4    # No longer used on the job control version of ppaxe
ENV GUNICORN_THREADS=4
ENV GUNICORN_TIMEOUT=600
ENV CORENLP_THREADS=4
ENV CORENLP_MAXMEM=4g
##
## Fake user... set up your own \n\
##
ENV PPAXE_EUSER="www"
ENV PPAXE_EPASSW="blabla"
ENV PPAXE_EMAIL="www@localhost"
##
## JOB links URL base... set up your own \n\
##
ENV URL_BASE=''
ENV APP_BASE=''

# Installing gunicorn
RUN pip install gunicorn

RUN \
  echo '#!/bin/bash\n\
echo "#-->ENV: USER ${PPAXE_EUSER}"\n\
echo "#-->ENV: EMAIL ${PPAXE_EMAIL}"\n\
export SPD="/stanford-corenlp-full-2017-06-09"\n\
\n\
export FLASK_APP=/ppaxe/ppaxe-app/ppaxeapp.py\n\
export PPAXE_CORENLP="http://127.0.0.1:9000"\n\
export PPAXE_DEBUG URL_BASE APP_BASE PPAXE_EUSER PPAXE_EPASSW PPAXE_EMAIL\n\
\n\
if [ "$PPAXE_DEBUG" = "1" ];\n\
  then\n\
    nohup java -Xms${CORENLP_MAXMEM} -Xmx${CORENLP_MAXMEM} \\\n\
               -cp $SPD/stanford-corenlp-3.8.0.jar:$SPD/stanford-english-corenlp-2017-06-09-models.jar \\\n\
               edu.stanford.nlp.pipeline.StanfordCoreNLPServer \\\n\
               -port 9000 -threads ${CORENLP_THREADS} \\\n\
               -serverProperties /ppaxe/ppaxe/data/server.properties \\\n\
             > /ppaxe/logs/core.log \\\n\
            2> /ppaxe/logs/core.err &\n\
    cd /ppaxe/ppaxe-app;\n\
    gunicorn -w ${GUNICORN_THREADS} \\\n\
             --bind=127.0.0.1:5000  \\\n\
             --timeout ${GUNICORN_TIMEOUT} \\\n\ 
             ppaxeapp:app \\\n\ 
             > /ppaxe/logs/gunicorn.log \\\n\
             2> /ppaxe/logs/gunicorn.err; \n\
  else\n\
    nohup java -Xms${CORENLP_MAXMEM} -Xmx${CORENLP_MAXMEM} \\\n\
               -cp $SPD/stanford-corenlp-3.8.0.jar:$SPD/stanford-english-corenlp-2017-06-09-models.jar \\\n\
               edu.stanford.nlp.pipeline.StanfordCoreNLPServer \\\n\
               -port 9000 -threads ${CORENLP_THREADS} \\\n\
               -serverProperties /ppaxe/ppaxe/data/server.properties \\\n\
            2> /dev/null 1>&2 &\n\
    cd /ppaxe/ppaxe-app;\n\
    gunicorn -w ${GUNICORN_THREADS} \\\n\
             --bind=127.0.0.1:5000  \\\n\
             --timeout ${GUNICORN_TIMEOUT} \\\n\ 
             ppaxeapp:app \\\n\ 
             2> /dev/null 1>&2; \n\
  fi\n' \
  > /ppaxe/entrypoint.sh \
  && chmod +x /ppaxe/entrypoint.sh

RUN cat /ppaxe/entrypoint.sh
    
EXPOSE 5000
    
ENTRYPOINT ["/ppaxe/entrypoint.sh"]
