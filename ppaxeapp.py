import os
from ppaxe import core
from ppaxe import report
from ppaxe import PubMedQueryError
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash


app = Flask(__name__) # create the application instance
app.config.from_object(__name__) # load config from this file


@app.route('/', methods=['GET'])
def home_form():
    '''
    Home of the ppaxe web application containing the form
    '''
    identifiers  = str()
    database     = str()
    results      = None
    nints        = None
    int_table    = None
    sum_table    = None
    error        = None
    if 'identifiers' in request.args:
        # Get Form parameters
        identifiers = request.args['identifiers']
        database = request.args['database']
        identifiers = identifiers.split(",")

        # Get articles from Pubmed or PMC
        source = str()
        try:
            query = core.PMQuery(ids=identifiers, database=database)
            query.get_articles()
        except PubMedQueryError:
            error = "PMQuery"
            return render_template('home.html', error=error,identifiers=identifiers, sum_table=sum_table, int_table=int_table, nints=nints, database=database)

        # Retrieve interactions from 'source'
        if database == "PUBMED":
            source = "abstract"
        else:
            source = "fulltext"
        for article in query.articles:
            article.predict_interactions(source)

        summary = report.ReportSummary(query)
        summary.graphsummary.makesummary()
        nints = summary.graphsummary.numinteractions
        if nints > 0:
            int_table = summary.graphsummary.table_to_html()
            sum_table = summary.summary_table()

    return render_template('home.html', identifiers=identifiers, sum_table=sum_table, int_table=int_table, nints=nints, database=database)
