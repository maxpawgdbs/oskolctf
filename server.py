import flask
import os

app = flask.Flask(__name__, template_folder= os.getcwd() + '/templates')
flags = open('flags.txt', 'r').readlines()

@app.route('/')
async def home():
    return '<h1>Welcome to OSKOLCTF</h1>'

@app.route('/flag')
async def flag():
    return "<h1>Ты нашёл секретный флаг! ockolctf{ockolctf}</h1>"

@app.route('/task0')
async def task0():
    return f"<h1>Привет! Это твой первый флаг! {flags[0].strip()}</h1>"

@app.route('/task1')
async def task1():
    return flask.render_template('task1.html', flag=flags[1].strip())

@app.route('/task2')
async def task2():
    response = flask.make_response(flask.render_template('task2.html'))
    response.set_cookie('flag', flags[2].strip(), max_age=60*60*24)
    return response

@app.route('/task3', methods=['GET', 'POST'])
async def task3():
    if flask.request.method == "GET":
        return flask.render_template('task3.html')
    elif flask.request.method == "POST":
        data = flask.request.data.decode('utf-8')
        if data == "b3Nrb2xjdGY=":
            return flags[3].strip()
        else:
            return "<h1>Wrong data, try again!</h1>"

if __name__ == '__main__':
    app.run('localhost', 8337)
