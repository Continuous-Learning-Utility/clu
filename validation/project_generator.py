"""Generates a minimal .csproj for C# validation with Unity DLL references."""

import os
import glob as glob_module


def generate_validation_csproj(
    csproj_path: str,
    unity_dll_path: str,
    lang_version: str = "9.0",
    target_framework: str = "netstandard2.1",
):
    """
    Generate a minimal .csproj that references Unity DLLs for validation builds.

    Args:
        csproj_path: Where to write the .csproj file.
        unity_dll_path: Directory containing Unity DLLs.
        lang_version: C# language version.
        target_framework: Target framework.
    """
    unity_dlls = glob_module.glob(os.path.join(unity_dll_path, "*.dll"))

    references = []
    for dll in unity_dlls:
        name = os.path.splitext(os.path.basename(dll))[0]
        dll_normalized = dll.replace("\\", "/")
        references.append(
            f'    <Reference Include="{name}">\n'
            f'      <HintPath>{dll_normalized}</HintPath>\n'
            f'    </Reference>'
        )

    references_block = "\n".join(references)

    csproj = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>{target_framework}</TargetFramework>
    <LangVersion>{lang_version}</LangVersion>
    <OutputType>Library</OutputType>
    <AllowUnsafeBlocks>false</AllowUnsafeBlocks>
    <NoWarn>0169;0649</NoWarn>
  </PropertyGroup>
  <ItemGroup>
{references_block}
  </ItemGroup>
  <ItemGroup>
    <Compile Include="Validate.cs" />
  </ItemGroup>
</Project>"""

    os.makedirs(os.path.dirname(csproj_path), exist_ok=True)
    with open(csproj_path, "w", encoding="utf-8") as f:
        f.write(csproj)
