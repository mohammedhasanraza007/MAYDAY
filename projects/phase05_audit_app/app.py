from flask import Flask
app = Flask(__name__)

@app.get('/')
def home():
    return 'ok'

@app.get('/hello')
def hello():
    return 'hello audit'
