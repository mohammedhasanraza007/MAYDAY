from flask import Flask, jsonify

app = Flask(__name__)

@app.get('/')
def index():
    return jsonify({'message': 'Hello from MAYDAY'})

if __name__ == '__main__':
    app.run(debug=True)
