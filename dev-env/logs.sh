#!/bin/bash
# View logs from the hop3 development environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$SCRIPT_DIR"

SERVICE="$1"

if [ -z "$SERVICE" ]; then
    echo "📜 Viewing all container logs (Ctrl+C to stop)..."
    echo ""
    docker compose logs -f
else
    case "$SERVICE" in
        supervisor)
            echo "📜 Viewing supervisor logs..."
            docker compose exec hop3-dev tail -f /var/log/supervisor/supervisord.log
            ;;
        nginx)
            echo "📜 Viewing nginx logs..."
            docker compose exec hop3-dev tail -f /var/log/nginx/access.log /var/log/nginx/error.log
            ;;
        uwsgi)
            echo "📜 Viewing uWSGI logs..."
            docker compose exec -u hop3 hop3-dev bash -c "tail -f /home/hop3/.hop3/apps/*/log/*.log"
            ;;
        postgres)
            echo "📜 Viewing PostgreSQL logs..."
            docker compose exec hop3-dev tail -f /var/log/postgresql/postgresql-14-main.log
            ;;
        *)
            echo "❌ Unknown service: $SERVICE"
            echo ""
            echo "Available services:"
            echo "  • supervisor  - Supervisor process manager logs"
            echo "  • nginx       - Nginx web server logs"
            echo "  • uwsgi       - uWSGI app server logs"
            echo "  • postgres    - PostgreSQL database logs"
            echo ""
            echo "Or run without arguments to see all container logs"
            exit 1
            ;;
    esac
fi
