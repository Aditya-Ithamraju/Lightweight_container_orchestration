import requests, time, socket, sys

LEADER_URL = "http://127.0.0.1:8000"


def find_free_port(start_port: int, max_tries: int = 200) -> int:
    port = int(start_port)
    for _ in range(max_tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            port += 1
        finally:
            try:
                s.close()
            except Exception:
                pass
    return int(start_port)


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else "nginx:alpine"
    port = find_free_port(6000)
    name = f"smoke-nginx-{int(time.time()*1000)}"

    body = {
        "image": image,
        "name": name,
        "port": port,
        "resources": {"cpu": 0.01, "mem_mb": 10, "min_energy": 0},
    }

    print(f"Deploying {image} as {name} on port {port}...")
    r = requests.post(f"{LEADER_URL}/deploy", json=body, timeout=60)
    print(r.status_code, r.text)

    if r.ok:
        print(f"Open: http://127.0.0.1:{port}/")
    else:
        print("Deployment failed. Check leader and agent logs. Common issues: docker not running, image not found, port in use")


if __name__ == "__main__":
    main()
