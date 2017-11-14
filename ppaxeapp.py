import os
from ppaxe import core
from ppaxe import report
import re
import smtplib
import mail
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


# APP INITIALIZATION
app = Flask(__name__) # create the application instance
app.config.from_object(__name__) # load config from this file


# FUNCTIONS
def create_pdf(pdf_data):
    '''
    Creates pdf file
    '''
    pdf = StringIO()
    pisa.CreatePDF(StringIO(pdf_data), pdf)
    return pdf

def send_mail(send_from, send_to, subject, text, files=None,
              server="127.0.0.1"):
    '''
    Returns message to be sent to ppaxe user
    '''
    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = send_to
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject
    part = MIMEBase('application', "octet-stream")
    part.set_payload(files[0].getvalue())
    #Encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="file.pdf"')
    msg.attach(part)
    return msg


# VIEWS
@app.route('/', methods=['GET', 'POST'])
def home_form():
    '''
    Home of the ppaxe web application containing the form
    '''
    identifiers = str()
    database    = str()
    response    = dict()

    if 'identifiers' in request.form:
        # Get Form parameters
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
            error = "PMQuery"

        # Retrieve interactions from 'source'
        if database == "PUBMED":
            source = "abstract"
        else:
            source = "fulltext"
        for article in query.articles:
            article.predict_interactions(source)

        summary = report.ReportSummary(query)
        summary.graphsummary.makesummary()
        summary.protsummary.makesummary()
        response['nints']  = summary.graphsummary.numinteractions
        response['nprots'] = summary.protsummary.totalprots
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
            response['pdf'] = create_pdf(render_template('pdf.html', identifiers=identifiers, response=response))
        if response['nprots'] > 0:
            response['prot_table'] = summary.protsummary.table_to_html()
        else:
            response['nprots'] = 0

        if email:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            #Next, log in to the server
            server.login("ppaxeatcompgen", mail.passw)
            #msg = "Hello THERE BEAUTIFUL!"
            # Create pdf not working
            msg = send_mail("ppaxeatcompgen@gmail.com", email, 'PPaxe results', "Download your results", [response['pdf']])
            server.sendmail("ppaxeatcompgen@gmail.com", email, msg.as_string())

    return render_template('home.html', identifiers=identifiers, response=response)


@app.route('/tutorial', methods=['GET'])
def tutorial():
    '''
    Tutorial page
    '''
    return render_template('tutorial.html')

@app.route('/about', methods=['GET'])
def about():
    '''
    About page
    '''
    return render_template('about.html')
