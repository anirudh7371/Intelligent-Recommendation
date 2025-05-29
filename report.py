import json
import requests
def fetch_report(url, output_file="report.json"):
    api_url = f"https://6id5r55ykwucnmkaw2wjzr4nhi0crzul.lambda-url.ap-southeast-2.on.aws/?url={url}"
    response = requests.get(api_url)

    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")

    if response.status_code == 200 or response.status_code == 299:
        try:
            data = response.json()
            with open(output_file, "w") as f:
                json.dump(data, f, indent=4)
            print(f"Report saved to {output_file}")
        except json.JSONDecodeError:
            print("Response is not valid JSON.")
    else:
        print(f"Failed to fetch data: {response.status_code}")
if __name__ == "__main__":
    url = "https://apexcabs.com.au/service"
    fetch_report(url)
