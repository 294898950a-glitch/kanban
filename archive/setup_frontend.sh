#!/bin/bash
set -e

# Load NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

echo "Current node version:"
node -v || true

nvm install 20
nvm use 20

echo "Node version after nvm use:"
node -v

npm config set registry https://registry.npmmirror.com

echo "Creating React project..."
# -- --template react-ts 明确参数，并在后续自行 install
npx create-vite@latest frontend --template react-ts
# 可能会有确认目录已存在的提示，这里最好预先 rm -rf frontend


echo "Installing ECharts and Axios..."
cd frontend
npm install echarts axios
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

echo "Done!"
