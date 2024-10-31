import runpod
import subprocess
import os
import requests
import tarfile
import io
import logging
import re

LOG_FORMAT = \
    '%(asctime)s [%(threadName)-16s] %(filename)27s:%(lineno)-4d %(levelname)7s| %(message)s'
logging.getLogger().setLevel(logging.INFO)

def parse_logs(s):
    return str(s).replace("depot", "docker").replace("DEPOT", "DOCKER").replace(str(os.environ["GIT_INTEGRATIONS_SECRET"]), "*****").replace("r2-registry-production.pierre-bastola.workers.dev", "*****")

token = "p.eyJ1IjogImZhYzExMWQ5LWNiOWUtNDEyMi1hNDA0LTU4ODY3NzM4ZjU1YSIsICJpZCI6ICJjYmE4ZTliYy1hOWI5LTQxYWEtODhkNi1lOGFmMmFkNDViMTIiLCAiaG9zdCI6ICJ1c19lYXN0In0.bsqX-pnatNjiTZDr68z_1myA_lUQczRlJT284yDewsM"

buffer = []
def send_to_tinybird(log, last_line, token):
    buffer.append(log)
    if len(buffer) == 4 or (last_line and len(buffer) > 0):
        pass
        # make the api call

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
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload

    bun_bin_dir = os.path.expanduser("~/.bun/bin")    
    envs["DEPOT_INSTALL_DIR"] = "/root/.depot/bin"
    envs["PATH"]=f"{bun_bin_dir}:$DEPOT_INSTALL_DIR:$PATH"

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
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload
    
    logging.info("Creating cache directory")
    try:
        os.makedirs(f"/app/{build_id}/cache", exist_ok=True)
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e)
        return return_payload
    builder_tkn = os.environ["GIT_INTEGRATIONS_SECRET"]

    envs["DEPOT_API_TOKEN"] = builder_tkn
    envs["DEPOT_INSTALL_DIR"] = "/root/.depot/bin"
    repo_dir = "/app/{}/temp/{}".format(build_id, extracted_dir)
    try: 
        process = subprocess.Popen('PATH="$DEPOT_INSTALL_DIR:$PATH" depot build -t {} {} --file {} --load --project {}'.format(
            cloudflare_destination, 
            repo_dir, 
            repo_dir + "/" + dockerfile_path, 
            project_id), cwd="/app", executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, env=envs)
        for line in iter(process.stdout.readline, ""):

            print(line, end="")
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong building the docker container: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = "Something went wrong. Please view the debug logs."
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = "Something went wrong. Please view the debug logs."
        return return_payload

    logging.info("Installing dependencies")
    envs["USERNAME_REGISTRY"] = username_registry
    envs["UUID"] = build_id
    envs["REGISTRY_JWT_TOKEN"] = jwt_token
    try:
        logging.info("Installing bun")
        subprocess.run("bun install", cwd="/app/serverless-registry/push", capture_output=True, env=envs, shell=True, executable="/bin/bash")
        logging.info("Installing bun again")
        subprocess.run("bun install", cwd="/app/serverless-registry", capture_output=True, env=envs, shell=True, executable="/bin/bash")
    except subprocess.CalledProcessError as e:
        error_msg = parse_logs(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
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
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(error_msg) + normal_out))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = parse_logs(error_msg + "\n" + normal_out)
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(parse_logs(e)))
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