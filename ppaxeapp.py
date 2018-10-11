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
from timeit import default_timer as timer
from StringIO import StringIO
import threading
import random
import cPickle as pickle
import sqlite3
import datetime
import time
import uuid


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
NJOBS = int(os.environ.get('PPAXE_THREADS', 4))
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


def connect_to_db():
    '''
    Returns connection to db
    '''
    db = sqlite3.connect('mydb')
    return db

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


def init_job(db, job):
    """
    Initializes job in database
    """
    start_time = datetime.datetime.now()
    db.execute(
        "INSERT into jobs(id, date, updated, progress) VALUES (?, ?, ?, ?)", 
        (job, start_time, start_time, 0) 
    )
    db.commit()
    return start_time


def get_end_time(db, job):
    """
    Returns end time of a given job
    """
    cursor = db.cursor()
    cursor.execute("SELECT updated from jobs WHERE id = ?", (job,))
    end_time = cursor.fetchone()
    return end_time[0]


def update_progress(db, job, progress):
    """
    Updates progress of job in database
    """
    db.execute("""
        UPDATE jobs
        SET progress = ?, updated = ?
        WHERE id = ?
    """, (progress, datetime.datetime.now(), job) )
    db.commit()


def update_percentage(db, job, perc):
    """
    Updates percentage of articles already analyzed
    """
    db.execute("""
        UPDATE jobs
        SET percentage = ?
        WHERE id = ?
    """, (perc, job))
    db.commit()


def get_progress(db, job):
    """
    Returns progress for a job
    """
    cursor = db.cursor()
    cursor.execute("SELECT progress from jobs WHERE id = ?", (job,))
    result = cursor.fetchone()[0]
    percentage = 0
    if result == 1:
        cursor.execute("SELECT percentage from jobs WHERE id = ?", (job,))
        try:
            percentage = int(cursor.fetchone()[0])
        except:
            percentage = 0
    return (result, percentage)


def create_response(summary, query):
    """
    Creates response object out of the summary.
    """
    response = dict()
    response['nints']  = summary.graphsummary.numinteractions
    response['nprots'] = summary.protsummary.totalprots

    if response['nprots'] > 0:
        response['prot_table'] = summary.protsummary.table_to_html()
    else:
        response['nprots'] = 0

    if query.database == "PUBMED":
        response['source'] = "Abstracts"
    else:
        response['source'] = "Full texts"
        
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
        response['database'] = query.database
        with app.app_context():
            response['pdf-plain'] = create_pdf(render_template('pdf.html', identifiers=query.ids, response=response))
        response['pdf'] = "data:application/pdf;base64," + base64.b64encode(response['pdf-plain'].getvalue())
    return response


# THREADING
# -----------------------------------------------------------------------
class ExportingThread(threading.Thread):
    def __init__(self, job_id, query, source):
        super(ExportingThread, self).__init__()
        self.job_id = job_id
        self.query = query
        self.source = source

    def run(self):
        db = connect_to_db()
        start_time = init_job(db, self.job_id)

        # Get Articles
        self.query.get_articles()
        update_progress(db, self.job_id, 1)

        # Predict Interactions
        total_articles = len(self.query.articles)
        curr_articles = 0
        percentage = 0
        prev_articles = 0
        for article in self.query:
            article.predict_interactions(self.source)

            curr_articles += 1
            percentage = (float(curr_articles) / float(total_articles)) * 100
            if int(curr_articles) - int(prev_articles) >= 5:
                prev_articles = curr_articles
                update_percentage(db, self.job_id, percentage)
        update_progress(db, self.job_id, 2)
        
        # Make Summary
        summary = report.ReportSummary(self.query)
        summary.graphsummary.makesummary()
        summary.protsummary.makesummary()
        update_progress(db, self.job_id, 3)

        # Create response object
        response = create_response(summary, self.query)
        response['start_time'] = start_time
        pickle_file = "tmp/%s_results.pkl" % self.job_id
        with open(pickle_file, 'wb') as p_fh:
            pickle.dump(response, p_fh)   
        update_progress(db, self.job_id, 4)


# VIEWS
# -----------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def home_form():
    identifiers = str()
    database    = str()
    response    = dict()
    response['search'] = False
    template = "base.html"
    if 'identifiers' in request.form:
        response['search'] = True
        template = "progress.html"
        job_id = int(str(int(time.time())) + str(random.randint(0, 100)))
        response['job_id'] = job_id
        identifiers = request.form['identifiers']
        database = request.form['database']
        identifiers = re.split(",|\n|\r", identifiers)
        identifiers = [ ident for ident in identifiers if ident ]
        if database == "PUBMED":
            source = "abstract"
        else:
            source = "fulltext"
        query = core.PMQuery(ids=identifiers, database=database)
        thread = ExportingThread(job_id, query, source)
        thread.start()
        # render progress template
        # which will do a jquery async query to /progess?job=XXXXX
        # Once progress == 3: redirect to /results?job=XXXX
    return render_template(template, identifiers=identifiers, response=response)


@app.route('/job/<int:job_id>')
def job(job_id):
    '''
    Allows users to check the progress of their job.
    '''
    db = connect_to_db()
    progress, percentage = get_progress(db, job_id)
    template = "progress.html"
    if progress < 4:
        # Not done yet
        # Redirect to progress page
        response['search'] = True
        response['job_id'] = job_id
    else:
        # Done
        # Redirect to results page
        template = "results.html"
        pickle_file = "tmp/%s_results.pkl" % job_id
        with open(pickle_file, 'rb') as p_fh:
            response = pickle.load(p_fh)
        response['search'] = True
        response['job_id'] = job_id
        response['end_time'] = get_end_time(db, job_id)
    return render_template(template, response=response)


@app.route('/progress/<int:job_id>')
def progress(job_id):
    '''
    Returns a string with the progress
        1 : Articles downloaded
        2 : Interactions retrieved
        3 : Report ready
        4 : Results ready
    '''
    db = connect_to_db()
    progress, percentage = get_progress(db, job_id)
    return jsonify(progress=progress, percentage=percentage)


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
