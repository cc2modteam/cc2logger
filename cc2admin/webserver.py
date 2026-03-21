from flask import Flask, render_template
from .logic import context
from cc2control.types import Blueprints, Loadout
app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html", context=context, blueprints=Blueprints, loadout=Loadout)