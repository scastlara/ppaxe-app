import os
from ppaxe import core
from ppaxe import report
import re
import smtplib
import base64
import datetime
from ppaxe import PubMedQueryError
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash
from xhtml2pdf import pisa
from StringIO import StringIO
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.MIMEBase import MIMEBase
from email.utils import COMMASPACE, formatdate
from email import Encoders
from pycorenlp import StanfordCoreNLP
from flask import jsonify
import requests
from xml.dom import minidom
from joblib import Parallel, delayed

class ReverseProxied(object):
    '''Wrap the application in this middleware and configure the 
    front-end server to add these headers, to let you quietly bind 
    this to a URL other than / and to an HTTP scheme that is 
    different than what is used locally.

    In nginx:
    location /myprefix {
        proxy_pass http://192.168.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Script-Name /myprefix;
        }

    :param app: the WSGI application
    '''
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]

        scheme = environ.get('HTTP_X_SCHEME', '')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        return self.app(environ, start_response)

class PrefixMiddleware(object):

    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):

        if environ['PATH_INFO'].startswith(self.prefix):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
            environ['SCRIPT_NAME'] = self.prefix
            return self.app(environ, start_response)
        else:
            start_response('404', [('Content-Type', 'text/plain')])
            return ["This url does not belong to the app.".encode()]

core.NLP = StanfordCoreNLP(os.environ.get('PPAXE_CORENLP','http://127.0.0.1:9000'))
app = Flask(__name__) # create the application instance
app.wsgi_app = ReverseProxied(app.wsgi_app)
NJOBS = os.environ.get('PPAXE_THREADS', 4)
# app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=environ.get('SCRIPT_NAME', ''))

# FUNCTIONS
# -----------------------------------------------------------------------
def create_pdf(pdf_data):
    '''
    Creates pdf file
    '''
    pdf = StringIO()
    pisa.CreatePDF(StringIO(pdf_data), pdf)
    return pdf

# -----------------
def send_mail(send_from, send_to, subject, attachment=None):
    '''
    Returns message to be sent to ppaxe user
    '''
    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = send_to
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject
    part = MIMEBase('application', "octet-stream")
    # Remove header
    part.set_payload(attachment.getvalue())
    #Encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="ppaxe-report.pdf"')
    msg.attach(part)
    return msg


def parallel_predict_interactions(sentence):
    '''
    Parallelizes the prediction of interactions
    '''
    sentence.annotate()
    sentence.get_candidates()
    for candidate in sentence.candidates:
        candidate.predict()
    return sentence


# VIEWS
# -----------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def home_form():
    '''
    Home of the ppaxe web application containing the form
    '''
    identifiers = str()
    database    = str()
    response    = dict()
    response['search'] = False

    if 'identifiers' in request.form:
        # Get Form parameters
        response['search'] = True
        identifiers = request.form['identifiers']
        database = request.form['database']
        email = request.form['email']
        identifiers = re.split(",|\n|\r", identifiers)
        identifiers = [ident for ident in identifiers if ident]

        # Get articles from Pubmed or PMC
        source = str()
        try:
            query = core.PMQuery(ids=identifiers, database=database)
            query.get_articles()
        except PubMedQueryError:
            response['error'] = "PMQuery"

        # Retrieve interactions from 'source'
        if database == "PUBMED":
            source = "abstract"
        else:
            source = "fulltext"
        for article in query.articles:
            article.extract_sentences(source=source)
            sentences = Parallel(n_jobs=NJOBS, backend="multiprocessing")(map(delayed(parallel_predict_interactions), article.sentences))
            article.sentences = sentences
        summary = report.ReportSummary(query)
        summary.graphsummary.makesummary()
        summary.protsummary.makesummary()
        response['nints']  = summary.graphsummary.numinteractions
        response['nprots'] = summary.protsummary.totalprots

        if response['nprots'] > 0:
            response['prot_table'] = summary.protsummary.table_to_html()
        else:
            response['nprots'] = 0

        if response['nints'] > 0:
            # Tables
            response['int_table'] = summary.graphsummary.table_to_html()
            response['sum_table'] = summary.summary_table()
            # JSON graph
            response['graph'] = summary.graphsummary.graph_to_json()
            # Plots
            response['plots'] = dict()
            response['plots']['j_int_plot'], response['plots']['j_prot_plot'], response['plots']['a_year_plot'] = summary.journal_plots()
            response['plots']['j_prot_plot'] = response['plots']['j_prot_plot'].getvalue().encode("base64").strip()
            response['plots']['j_int_plot']  = response['plots']['j_int_plot'].getvalue().encode("base64").strip()
            response['plots']['a_year_plot'] = response['plots']['a_year_plot'].getvalue().encode("base64").strip()
            response['today'] = datetime.date.today()
            response['database'] = database
            response['pdf-plain'] = create_pdf(render_template('pdf.html', identifiers=identifiers, response=response))
            response['pdf'] = "data:application/pdf;base64," + base64.b64encode(response['pdf-plain'].getvalue())


            if email:
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(os.environ.get('PPAXE_EUSER', "dummy"), os.environ.get('PPAXE_EPASSW', "ymmud"))
                msg = send_mail(os.environ.get('PPAXE_EMAIL', "dummy@email.com"), email, 'PPaxe results', response['pdf-plain'])
                server.sendmail(os.environ.get('PPAXE_EMAIL', "dummy@email.com"), email, msg.as_string())

    return render_template('home.html', identifiers=identifiers, response=response)


@app.route('/querypubmed', methods=['GET'])
def querypubmed():
    '''
    Queries PubMed and returns the pubmed identifiers
    '''    
    response    = dict()
    response['error'] = True
    if request.is_xhr:
        query = request.args.get('query')
        req = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&rettype=count&term=%s" % (query) )
        if req.status_code == 200:
            md = minidom.parseString(req.text)
            count = md.getElementsByTagName('Count')
            count = count[0].firstChild.nodeValue
            req = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmax=%s&term=%s" % (count, query) )
            if req.status_code == 200:
                md = minidom.parseString(req.text)
                theids = md.getElementsByTagName('Id')
                try:
                    theids = [ iden.firstChild.nodeValue for iden in theids ]
                except Exception:
                    response['error'] = True
                if theids:
                    response['identifiers'] = theids
                    response['error'] = False
        return jsonify(response)


# -----------------
@app.route('/tutorial', methods=['GET'])
def tutorial():
    '''
    Tutorial page
    '''
    return render_template('tutorial.html')



@app.route('/download', methods=['GET'])
def download():
    '''
    download page
    '''
    return render_template('download.html')


# -----------------
@app.route('/about', methods=['GET'])
def about():
    '''
    About page
    '''
    return render_template('about.html')
