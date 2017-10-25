import os
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash


app = Flask(__name__) # create the application instance :)
app.config.from_object(__name__) # load config from this file


@app.route('/', methods=['GET'])
def home_form():
    '''
    Home of the ppaxe web application containing the form
    '''
    identifiers = str()
    database    = str()
    if 'identifiers' in request.args:
        identifiers = request.args['identifiers']
        database = request.args['database']
    return render_template('home.html', identifiers=identifiers, database=database)
