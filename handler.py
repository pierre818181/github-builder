import sys
import runpod
import subprocess
import os
import requests
import tarfile
import io
import logging
import re
import requests
import json
from datetime import datetime

LOG_FORMAT = \
    '%(asctime)s [%(threadName)-16s] %(filename)27s:%(lineno)-4d %(levelname)7s| %(message)s'
logging.getLogger().setLevel(logging.INFO)

def parse_logs(s):
    return str(s).replace("depot", "******").replace("DEPOT", "******").replace(str(os.environ["GIT_INTEGRATIONS_SECRET"]), "*****").replace("r2-registry-production.pierre-bastola.workers.dev", "*****")

tinybird_auth_token = os.environ["TINYBIRD_APPEND_ONLY_TOKEN"]

tinybird_url = "https://api.us-east.tinybird.co/v0"
buffer = []
def send_to_tinybird(build_id, level, log, last_line):
    if not log or len(log) == 0:
        return True
    global buffer
    log = { 
        "buildId": build_id, 
        "level": level, 
        "workerId": os.environ["RUNPOD_POD_ID"], 
        "message": log,
        "timestamp": datetime.now().isoformat()
    }
    buffer.append(parse_logs(log))
    if len(buffer) == 4 or (last_line and len(buffer) > 0):
        url = f"{tinybird_url}/events?wait=true&name=github_build_logs"
        print(json.dumps(record) for record in buffer)
        data = "\n".join([json.dumps(record).replace('"', '') for record in buffer])
        headers = {
            "Authorization": f"Bearer {tinybird_auth_token}",
            "Content-Type": "text/plain",
        }
        print(data)
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()
        buffer = []

    return True

def build_image(job):
    job_input = job["input"]
    dockerfile_path = job_input["dockerfile_path"]
    build_id = job_input["build_id"]
    cloudflare_destination = job_input["cloudflare_destination"]
    github_repo = job_input["github_repo"]
    github_repo = github_repo.replace(".git", "")
    auth_token = job_input["auth_token"]
    ref = job_input["ref"]
    jwt_token = job_input["jwt_token"]
    username_registry = job_input["username_registry"]
    refresh_worker = job_input.get("refresh_worker", "true")
    project_id = job_input["project_id"]
    refresh_worker_flag = True
    if refresh_worker == "false":
        refresh_worker_flag = False

    return_payload = {
        "refresh_worker": refresh_worker_flag,
        "token": jwt_token,
        "status": "succeeded",
        "build_id": build_id,
        "image_name": cloudflare_destination
    }

    envs = os.environ.copy()
    try:
        install_command = "curl -fsSL https://bun.sh/install | bash"
        subprocess.run(install_command, shell=True, executable="/bin/bash", check=True, capture_output=True, env=envs)
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong while installing bun: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while installing bun: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload

    bun_bin_dir = os.path.expanduser("~/.bun/bin")
    if bun_bin_dir not in sys.path:
        sys.path.append(bun_bin_dir) 
    envs["DEPOT_INSTALL_DIR"] = "/root/.depot/bin"
    if "/root/.depot/bin" not in sys.path:
        sys.path.append("/root/.depot/bin")
    envs["PATH"]=f"{bun_bin_dir}:$PATH"

    if envs["TINYBIRD_APPEND_ONLY_TOKEN"] is None:
        logging.error("Tinybird append only log has not been added.")
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload

    logging.info(f"Downloading {github_repo} at {ref}")
    api_url = f"https://api.github.com/repos/{github_repo.split('/')[-2]}/{github_repo.split('/')[-1]}/tarball/{ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {auth_token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        response = requests.get(api_url, headers=headers, stream=True)
        response.raise_for_status()
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload

    logging.info(f"Extracting {github_repo} at {ref}")
    temp_dir = f"/app/{build_id}/temp"
    try:
        os.makedirs(temp_dir, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
            tar.extractall(path=temp_dir)
        extracted_dir = next(os.walk(temp_dir))[1][0]
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong while extracting repo: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while extracting repo: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload
    
    logging.info("Creating cache directory")
    try:
        os.makedirs(f"/app/{build_id}/cache", exist_ok=True)
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong while creating cache directory: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while creating cache directory: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload
    builder_tkn = os.environ["GIT_INTEGRATIONS_SECRET"]

    envs["DEPOT_API_TOKEN"] = builder_tkn
    envs["DEPOT_INSTALL_DIR"] = "/root/.depot/bin"
    if "/root/.depot/bin" not in sys.path:
        sys.path.append("/root/.depot/bin")

    repo_dir = "/app/{}/temp/{}".format(build_id, extracted_dir)
    try: 
        command = [
            f'DEPOT_INSTALL_DIR="/root/.depot/bin" && /root/.depot/bin/depot build -t {cloudflare_destination} {repo_dir} --file {repo_dir}/{dockerfile_path}  --load --project {project_id}'
        ]
        process = subprocess.Popen(command, 
                                   cwd="/app", 
                                   bufsize=1, 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE,
                                   env=envs,
                                   text=True, 
                                   shell=True,
                                   executable="/bin/bash")
        with process.stdout as output:
            for line in output:
                content = line.strip()
                print(f"{content}")
                send_to_tinybird(build_id, "INFO", content, False)
        with process.stderr as error:
            for line in error:
                content = line.strip()
                print(f"{content}")
                send_to_tinybird(build_id, "ERROR", content, False)
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong building the docker image: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = "Something went wrong. Please view the debug logs."
        return return_payload
    except Exception as e:
        logging.error("Something went wrong building the docker image: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = "Something went wrong. Please view the debug logs."
        return return_payload
    send_to_tinybird(build_id, "INFO", str("Build complete."), True)

    logging.info("Installing dependencies")
    envs["USERNAME_REGISTRY"] = username_registry
    envs["UUID"] = build_id
    envs["REGISTRY_JWT_TOKEN"] = jwt_token
    envs["PATH"]=f"{bun_bin_dir}:$DEPOT_INSTALL_DIR:$PATH"
    try:
        logging.info("Installing bun")
        subprocess.run("bun install", cwd="/app/serverless-registry/push", capture_output=True, env=envs, shell=True, executable="/bin/bash")
        logging.info("Installing bun again")
        subprocess.run("bun install", cwd="/app/serverless-registry", capture_output=True, env=envs, shell=True, executable="/bin/bash")
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong while installing local dependencies: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while installing local dependencies: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload

    logging.info("Pushing image to registry")
    run_command = "REGISTRY_JWT_TOKEN={} USERNAME_REGISTRY=pierre bun run index.ts {}".format(jwt_token, cloudflare_destination)
    try:
        subprocess.run(run_command, cwd="/app/serverless-registry/push", capture_output=True, env=envs, shell=True, check=True, executable="/bin/bash")
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        normal_out = parse_logs(e.stdout)
        logging.error("Something went wrong while pushing to registry: {}".format(parse_logs(error_msg) + normal_out))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(error_msg + "\n" + normal_out)
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while pushing to registry: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload
    
    # logging.info(f"Cleaning up")
    # try:
    #     subprocess.run("rm -rf /app/{}".format(build_id), executable="/bin/bash", capture_output=True, shell=True, env=envs, check=True)
    # except subprocess.CalledProcessError as e:
    #     error_msg = parse_logs(e.stderr)
    #     logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(error_msg)))
    #     return_payload["status"] = "failed"
    #     return_payload["error_msg"] = parse_logs(e) + error_msg
    #     return return_payload
    # except Exception as e:
    #     logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
    #     return_payload["status"] = "failed"
    #     return_payload["error_msg"] = parse_logs(e)
    #     return return_payload

    return return_payload

runpod.serverless.start({"handler": build_image})