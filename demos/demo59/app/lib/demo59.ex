defmodule Demo59.Application do
  use Application

  def start(_type, _args) do
    port = String.to_integer(System.get_env("PORT") || "4000")

    children = [
      {Plug.Cowboy, scheme: :http, plug: Demo59.Router, options: [port: port]}
    ]

    opts = [strategy: :one_for_one, name: Demo59.Supervisor]
    Supervisor.start_link(children, opts)
  end
end

defmodule Demo59.Router do
  use Plug.Router

  plug :match
  plug :dispatch

  get "/" do
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Elixir Prerequisite Test</title></head>
    <body style="font-family: sans-serif; text-align: center; padding: 2rem;">
      <h1>Elixir Prerequisites OK</h1>
      <p>Elixir version: #{System.version()}</p>
      <p>OTP version: #{System.otp_release()}</p>
    </body>
    </html>
    """
    send_resp(conn, 200, html)
  end

  get "/up" do
    send_resp(conn, 200, "OK")
  end

  get "/health" do
    response = Jason.encode!(%{
      status: "ok",
      elixir_version: System.version(),
      otp_version: System.otp_release()
    })
    conn
    |> put_resp_content_type("application/json")
    |> send_resp(200, response)
  end

  match _ do
    send_resp(conn, 404, "Not Found")
  end
end
