from app import app, socketio

if __name__ == "__main__":
    socketio.run(
        app,
        host=app.config["app"]["ip"],
        port=app.config["app"]["port"],
        debug=app.config["DEBUG"],
    )