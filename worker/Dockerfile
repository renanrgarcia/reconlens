FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY ReconLens.sln ./
COPY src/ReconLens.Worker/ReconLens.Worker.csproj src/ReconLens.Worker/
COPY tests/ReconLens.Worker.Tests/ReconLens.Worker.Tests.csproj tests/ReconLens.Worker.Tests/
RUN dotnet restore
COPY src/ src/
RUN dotnet publish src/ReconLens.Worker -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/runtime:10.0
WORKDIR /app
COPY --from=build /app .
ENTRYPOINT ["dotnet", "ReconLens.Worker.dll"]
