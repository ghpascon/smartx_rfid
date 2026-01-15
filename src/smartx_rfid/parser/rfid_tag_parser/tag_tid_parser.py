"""
RFID Tag TID Parser
Módulo para parsing e análise de TID (Tag Identifier) de tags RFID.

Este módulo fornece funcionalidades para converter TID hexadecimal em informações
estruturadas sobre tags RFID, incluindo fabricante, modelo, número serial e outras
características técnicas.

Baseado na implementação original em C# TagTidParser.cs

Autor: Conversão de C# para Python
Data: 2025-07-04
Versão: 1.0.0
"""

from typing import Dict, Union
from .exceptions import TagTidParserError, InvalidTidError


class TagTidParser:
    """
    Parser para TID (Tag Identifier) de tags RFID.

    Esta classe permite extrair informações detalhadas de tags RFID a partir
    do TID (Tag Identifier) de 96 bits, incluindo:

    - Número serial de 40 bits (hexadecimal e decimal)
    - Identificação do fabricante
    - Modelo da tag
    - Número do modelo (TMN - Tag Model Number)
    - ID da série Monza (para tags Impinj)
    - Detecção automática do algoritmo de extração

    Suporte para fabricantes:
    - Impinj (Monza R6, M700, M800, Monza 4/5 Series)
    - NXP (UCODE 7, 8, 9)
    - Fallback universal para fabricantes desconhecidos

    Exemplo:
        >>> parser = TagTidParser("E2801190000000000000000A")
        >>> print(parser.get_vendor_from_tid())
        'Impinj Monza R6'
        >>> print(parser.get_tag_model_name())
        'Impinj M750'
        >>> print(parser.get_40bit_serial_hex())
        '000000000A'
    """

    # Prefixos conhecidos de TID mapeados para fabricantes
    # Baseado nos primeiros 4 bytes (32 bits) do TID
    KNOWN_TID_PREFIXES: Dict[str, str] = {
        # Impinj Monza R6 Series
        "E2801190": "Impinj Monza R6",
        # Impinj M700 Series
        "E2801191": "Impinj M730",
        "E28011A0": "Impinj M770",
        # Impinj M800 Series
        "E28011B0": "Impinj M830/M850",
        # NXP UCODE 9 Series
        "E2806915": "NXP UCODE 9",
        "E2806995": "NXP UCODE 9",
        # Adicione mais conforme necessário
        # Formato: "XXXXXXXX": "Fabricante Modelo"
    }

    # Mapeamento de TMN (Tag Model Number) para nomes de modelos
    # TMN é extraído dos bits 11-0 dos bytes 2-3 do TID
    TAG_MODEL_MAP: Dict[int, str] = {
        # Impinj M700 Series
        0x190: "Impinj M750",  # TMN 0x190 = Impinj M750
        0x191: "Impinj M730",  # TMN 0x191 = Impinj M730
        0x1A0: "Impinj M770",  # TMN 0x1A0 = Impinj M770
        # Impinj M800 Series
        0x1B0: "Impinj M830/M850",  # TMN 0x1B0 = Impinj M830/M850
        # Impinj Monza R6 Family
        0x120: "Impinj Monza R6",  # TMN 0x120 = Impinj Monza R6
        0x121: "Impinj Monza R6-A",  # TMN 0x121 = Impinj Monza R6-A
        0x122: "Impinj Monza R6-P",  # TMN 0x122 = Impinj Monza R6-P
        # Impinj Monza 4 Series
        0x0B2: "Impinj Monza 4D",  # TMN 0x0B2 = Impinj Monza 4D
        0x0B3: "Impinj Monza 4E",  # TMN 0x0B3 = Impinj Monza 4E
        0x0B4: "Impinj Monza 4U",  # TMN 0x0B4 = Impinj Monza 4U
        0x0B5: "Impinj Monza 4QT",  # TMN 0x0B5 = Impinj Monza 4QT
        # Impinj Monza 5 Series
        0x0C0: "Impinj Monza 5",  # TMN 0x0C0 = Impinj Monza 5
        # NXP UCODE 9 Series
        0x915: "NXP UCODE 9",  # TMN 0x915 = NXP UCODE 9 (variante 1)
        0x995: "NXP UCODE 9",  # TMN 0x995 = NXP UCODE 9 (variante 2)
        # NXP UCODE 8 Series (prefixos estimados)
        0x910: "NXP UCODE 8",  # TMN 0x910 = NXP UCODE 8
        0x990: "NXP UCODE 8",  # TMN 0x990 = NXP UCODE 8
        # NXP UCODE 7 Series (valor comum)
        0x970: "NXP UCODE 7",  # TMN 0x970 = NXP UCODE 7
        # Adicione mais modelos conforme necessário
        # Formato: 0xXXX: "Fabricante Modelo Específico"
    }

    def __init__(self, tid_hex: str):
        """
        Inicializa o parser com um TID em formato hexadecimal.

        Args:
            tid_hex (str): TID em formato hexadecimal. Deve ter exatamente 24
                          caracteres (96 bits). Espaços e hífens são automaticamente
                          removidos. Case insensitive.

        Raises:
            InvalidTidError: Se o TID for None, vazio ou apenas espaços
            ValueError: Se o TID não tiver 24 caracteres hexadecimais ou
                       contiver caracteres inválidos

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000A")
            >>> parser = TagTidParser("E2-80-11-90-00-00-00-00-00-00-00-0A")
            >>> parser = TagTidParser("e2 80 11 90 00 00 00 00 00 00 00 0a")
        """
        if tid_hex is None or not str(tid_hex).strip():
            raise InvalidTidError("TID não pode ser vazio ou nulo")

        # Normalizar TID: remover espaços, hífens e converter para maiúscula
        tid_hex = str(tid_hex).replace(" ", "").replace("-", "").upper().strip()

        if len(tid_hex) != 24:
            raise ValueError("TID deve ter 24 caracteres hexadecimais (96 bits)")

        try:
            # Converter para bytes e validar caracteres hexadecimais
            self._tid = bytes.fromhex(tid_hex)
        except ValueError:
            raise ValueError("TID contém caracteres hexadecimais inválidos")

        # Armazenar TID original normalizado para referência
        self._tid_hex = tid_hex
        # Flag para indicar se o objeto foi "descartado"
        self._disposed = False

    def get_40bit_serial_hex(self) -> str:
        """
        Extrai o número serial de 40 bits em formato hexadecimal.

        O algoritmo de extração varia baseado no fabricante detectado:
        - NXP UCODE 9: Extrai dos bytes 7-11 (posições específicas)
        - Impinj: Extrai dos bytes 6-10 (padrão Impinj)
        - Fallback: Extrai dos últimos 5 bytes (para fabricantes desconhecidos)

        Returns:
            str: Número serial de 40 bits em formato hexadecimal maiúsculo
                 (exatamente 10 caracteres)

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000A")
            >>> parser.get_40bit_serial_hex()
            '000000000A'
        """
        if self._disposed:
            raise TagTidParserError("Objeto TagTidParser já foi descartado")

        if self._is_impinj_tid():
            serial = 0
            if self._is_m700_series() or self._is_m800_series():
                serial = (
                    ((self._tid[6] & 0x3F) << 32)
                    | (self._tid[7] << 24)
                    | (self._tid[8] << 16)
                    | (self._tid[9] << 8)
                    | self._tid[10]
                )
            elif self._is_r6_series():
                serial = self._get_r6_series_38bit_serial()
            return f"{serial:010X}"

        if self._is_nxp_ucode9_tid():
            serial = 0
            for i in range(7, 12):
                serial = (serial << 8) | self._tid[i]
            return f"{serial:010X}"

        # Algoritmo fallback para fabricantes desconhecidos
        # Extrai dos últimos 5 bytes
        return self._get_fallback_serial_hex()

    def get_40bit_serial_decimal(self) -> int:
        """
        Extrai o número serial de 40 bits em formato decimal.

        Returns:
            int: Número serial de 40 bits como inteiro decimal (0 a 1099511627775)

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000A")
            >>> parser.get_40bit_serial_decimal()
            10
        """
        hex_serial = self.get_40bit_serial_hex()
        return int(hex_serial, 16)

    def _get_fallback_serial_hex(self) -> str:
        """
        Método fallback para extrair serial dos últimos 5 bytes.

        Usado quando o fabricante não é reconhecido ou não tem algoritmo específico.

        Returns:
            str: Serial em formato hexadecimal maiúsculo (10 caracteres)
        """
        # Extrair últimos 5 bytes (índices 7, 8, 9, 10, 11)
        return self._tid[-5:].hex().upper()

    def _is_r6_series(self) -> bool:
        """Verifica se o TMN corresponde a um chip da família Monza R6."""
        tmn = ((self._tid[2] & 0x0F) << 8) | self._tid[3]
        return tmn in {0x120, 0x121, 0x122, 0x170}

    def _is_m700_series(self) -> bool:
        """Verifica se o TMN corresponde a um chip da série M700."""
        tmn = ((self._tid[2] & 0x0F) << 8) | self._tid[3]
        return tmn in {0x190, 0x191, 0x1A0, 0x1A2}

    def _is_m800_series(self) -> bool:
        """Verifica se o TMN corresponde a um chip da série M800."""
        tmn = ((self._tid[2] & 0x0F) << 8) | self._tid[3]
        return tmn == 0x1B0

    def _get_r6_series_38bit_serial(self) -> int:
        """Obtém o serial de 38 bits para tags Monza R6."""
        if not self._is_r6_series():
            raise TagTidParserError("Tag não é da família Monza R6")
        return (
            ((self._tid[6] & 0x3F) << 32)
            | (self._tid[7] << 24)
            | (self._tid[8] << 16)
            | (self._tid[9] << 8)
            | self._tid[10]
        )

    def _is_impinj_tid(self) -> bool:
        """
        Verifica se o TID pertence a uma tag Impinj.

        Critério de identificação Impinj:
        - Byte 0: 0xE2 (ISO/IEC 18000-6C)
        - Byte 1: 0x80 (Allocation Class)
        - Byte 2: 0x1X (bits 7-4 = 0x1, bits 3-0 = qualquer)

        Returns:
            bool: True se for uma tag Impinj, False caso contrário
        """
        return self._tid[0] == 0xE2 and self._tid[1] == 0x80 and (self._tid[2] >> 4) == 0x1

    def _is_nxp_ucode9_tid(self) -> bool:
        """
        Verifica se o TID pertence a uma tag NXP UCODE 9.

        Critério de identificação NXP UCODE 9:
        - Byte 0: 0xE2 (ISO/IEC 18000-6C)
        - Byte 1: 0x80 (Allocation Class)
        - Byte 2: 0x69 (identificador UCODE 9)
        - Byte 3: 0x15 ou 0x95 (variantes conhecidas)

        Returns:
            bool: True se for uma tag NXP UCODE 9, False caso contrário
        """
        return (
            self._tid[0] == 0xE2
            and self._tid[1] == 0x80
            and self._tid[2] == 0x69
            and (self._tid[3] == 0x15 or self._tid[3] == 0x95)
        )

    def get_monza_series_id(self) -> int:
        """
        Extrai o ID da série Monza (específico para tags Impinj).

        O ID da série é codificado nos bits 7-6 do byte 10 (índice 10).
        Valores possíveis: 0, 1, 2, 3

        Returns:
            int: ID da série Monza (0-3)

        Note:
            Este método só é relevante para tags Impinj. Para outras tags,
            o valor pode não ter significado específico.

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000040")  # série 1
            >>> parser.get_monza_series_id()
            1
        """
        # Extrair bits 7-6 do byte 10
        return (self._tid[10] >> 6) & 0b11

    def get_tag_model_number(self) -> str:
        """
        Extrai o número do modelo da tag (TMN - Tag Model Number).

        O TMN é codificado nos bits 11-0 dos bytes 2-3:
        - Bits 3-0 do byte 2 (nibble baixo)
        - Bits 7-0 do byte 3 (byte completo)

        Returns:
            str: Número do modelo em formato hexadecimal maiúsculo (3 caracteres)

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000A")
            >>> parser.get_tag_model_number()
            '190'
        """
        # Combinar bits 3-0 do byte 2 com byte 3 completo
        # (byte2 & 0x0F) << 8 | byte3
        tmn = ((self._tid[2] & 0x0F) << 8) | self._tid[3]
        return f"{tmn:03X}"

    def get_tag_model_name(self) -> str:
        """
        Obtém o nome descritivo do modelo da tag.

        Consulta o dicionário TAG_MODEL_MAP usando o TMN extraído.
        Se o modelo não for reconhecido, retorna uma string descritiva
        com o TMN em hexadecimal.

        Returns:
            str: Nome do modelo ou "Desconhecido (TMN 0xXXX)" se não encontrado

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000A")
            >>> parser.get_tag_model_name()
            'Impinj M750'
            >>> parser = TagTidParser("E280FF00000000000000000A")  # TMN desconhecido
            >>> parser.get_tag_model_name()
            'Desconhecido (TMN 0xF00)'
        """
        # Extrair TMN
        tmn = ((self._tid[2] & 0x0F) << 8) | self._tid[3]

        # Buscar no mapeamento ou retornar desconhecido
        return self.TAG_MODEL_MAP.get(tmn, f"Desconhecido (TMN 0x{tmn:03X})")

    def get_vendor_from_tid(self) -> str:
        """
        Identifica o fabricante baseado no prefixo do TID.

        Utiliza os primeiros 4 bytes (32 bits) do TID para identificar
        o fabricante consultando o dicionário KNOWN_TID_PREFIXES.

        Returns:
            str: Nome do fabricante ou "Desconhecido" se não encontrado

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000A")
            >>> parser.get_vendor_from_tid()
            'Impinj Monza R6'
            >>> parser = TagTidParser("FF00AA00000000000000000A")  # Prefixo desconhecido
            >>> parser.get_vendor_from_tid()
            'Desconhecido'
        """
        # Extrair primeiros 4 bytes como string hexadecimal
        prefix = self._tid[:4].hex().upper()

        # Buscar no dicionário de prefixos conhecidos
        return self.KNOWN_TID_PREFIXES.get(prefix, "Desconhecido")

    def get_tid_info(self) -> Dict[str, Union[str, int, bool, None]]:
        """
        Retorna todas as informações extraídas do TID em um dicionário estruturado.

        Este método combina todos os outros métodos da classe para fornecer
        uma visão completa das informações da tag em um formato conveniente.

        Returns:
            dict: Dicionário com todas as informações da tag contendo:
                - tid (str): TID original em hexadecimal maiúsculo
                - vendor (str): Nome do fabricante
                - model_name (str): Nome do modelo
                - model_number (str): Número do modelo (TMN) em hex
                - serial_hex (str): Serial de 40 bits em hexadecimal
                - serial_decimal (int): Serial de 40 bits em decimal
                - monza_series_id (int|None): ID da série Monza (apenas Impinj)
                - is_impinj (bool): True se for tag Impinj
                - is_nxp_ucode9 (bool): True se for NXP UCODE 9

        Examples:
            >>> parser = TagTidParser("E2801190000000000000000A")
            >>> info = parser.get_tid_info()
            >>> print(info['vendor'])
            'Impinj Monza R6'
            >>> print(info['serial_decimal'])
            10
        """
        # Determinar se é Impinj para incluir Monza Series ID
        is_impinj = self._is_impinj_tid()
        monza_series_id = self.get_monza_series_id() if is_impinj else None

        return {
            "tid": self._tid_hex,
            "vendor": self.get_vendor_from_tid(),
            "model_name": self.get_tag_model_name(),
            "model_number": self.get_tag_model_number(),
            "serial_hex": self.get_40bit_serial_hex(),
            "serial_decimal": self.get_40bit_serial_decimal(),
            "monza_series_id": monza_series_id,
            "is_impinj": is_impinj,
            "is_nxp_ucode9": self._is_nxp_ucode9_tid(),
        }

    def __str__(self) -> str:
        """
        Representação string do parser.

        Returns:
            str: String descritiva com TID, fabricante e modelo
        """
        vendor = self.get_vendor_from_tid()
        model = self.get_tag_model_name()
        return f"TagTidParser(TID={self._tid_hex}, Vendor={vendor}, Model={model})"

    def __repr__(self) -> str:
        """
        Representação para debug do parser.

        Returns:
            str: String de representação para debug
        """
        return f"TagTidParser('{self._tid_hex}')"

    def __eq__(self, other) -> bool:
        """
        Compara dois parsers pela igualdade do TID.

        Args:
            other: Outro objeto TagTidParser para comparação

        Returns:
            bool: True se os TIDs forem iguais
        """
        if not isinstance(other, TagTidParser):
            return False
        return self._tid_hex == other._tid_hex

    def __hash__(self) -> int:
        """
        Hash baseado no TID para uso em sets e dicts.

        Returns:
            int: Hash do TID
        """
        return hash(self._tid_hex)

    def dispose(self) -> None:
        """Descarta o objeto limpando os dados do TID."""
        if not self._disposed:
            self._tid = b""
            self._disposed = True


# ============================================================================
# FUNÇÕES DE CONVENIÊNCIA PARA USO DIRETO
# ============================================================================


def parse_tid(tid_hex: str) -> Dict[str, Union[str, int, bool, None]]:
    """
    Função de conveniência para parsing rápido de TID.

    Esta função cria um TagTidParser temporário e retorna todas as
    informações extraídas em um dicionário.

    Args:
        tid_hex (str): TID em formato hexadecimal (24 caracteres)

    Returns:
        dict: Dicionário com todas as informações da tag
               (mesmo formato que TagTidParser.get_tid_info())

    Raises:
        InvalidTidError: Se o TID for inválido
        ValueError: Se o TID tiver formato incorreto

    Examples:
        >>> info = parse_tid("E2801190000000000000000A")
        >>> print(info['model_name'])
        'Impinj M750'
        >>> print(info['serial_hex'])
        '000000000A'
    """
    parser = TagTidParser(tid_hex)
    return parser.get_tid_info()


def get_serial_from_tid(tid_hex: str, format_type: str = "hex") -> Union[str, int]:
    """
    Extrai apenas o número serial do TID no formato especificado.

    Função de conveniência para quando apenas o serial é necessário,
    evitando criar o parser completo.

    Args:
        tid_hex (str): TID em formato hexadecimal (24 caracteres)
        format_type (str): Formato do retorno - "hex" ou "decimal"

    Returns:
        str: Serial em hexadecimal se format_type="hex"
        int: Serial em decimal se format_type="decimal"

    Raises:
        InvalidTidError: Se o TID for inválido
        ValueError: Se o TID tiver formato incorreto ou format_type inválido

    Examples:
        >>> get_serial_from_tid("E2801190000000000000000A", "hex")
        '000000000A'
        >>> get_serial_from_tid("E2801190000000000000000A", "decimal")
        10
    """
    parser = TagTidParser(tid_hex)

    if format_type.lower() == "decimal":
        return parser.get_40bit_serial_decimal()
    elif format_type.lower() == "hex":
        return parser.get_40bit_serial_hex()
    else:
        raise ValueError(f"format_type deve ser 'hex' ou 'decimal', recebido: '{format_type}'")


def validate_tid(tid_hex: str) -> bool:
    """
    Valida se um TID tem formato válido sem fazer o parsing completo.

    Args:
        tid_hex (str): TID para validar

    Returns:
        bool: True se o TID for válido, False caso contrário

    Examples:
        >>> validate_tid("E2801190000000000000000A")
        True
        >>> validate_tid("INVALID")
        False
    """
    try:
        TagTidParser(tid_hex)
        return True
    except (InvalidTidError, ValueError):
        return False


def get_vendor_from_tid(tid_hex: str) -> str:
    """
    Extrai apenas o fabricante do TID.

    Função de conveniência para identificação rápida do fabricante.

    Args:
        tid_hex (str): TID em formato hexadecimal

    Returns:
        str: Nome do fabricante ou "Desconhecido"

    Examples:
        >>> get_vendor_from_tid("E2801190000000000000000A")
        'Impinj Monza R6'
    """
    parser = TagTidParser(tid_hex)
    return parser.get_vendor_from_tid()


def get_model_from_tid(tid_hex: str) -> str:
    """
    Extrai apenas o modelo do TID.

    Função de conveniência para identificação rápida do modelo.

    Args:
        tid_hex (str): TID em formato hexadecimal

    Returns:
        str: Nome do modelo

    Examples:
        >>> get_model_from_tid("E2801190000000000000000A")
        'Impinj M750'
    """
    parser = TagTidParser(tid_hex)
    return parser.get_tag_model_name()


# ============================================================================
# CÓDIGO DE EXEMPLO E DEMONSTRAÇÃO
# ============================================================================

if __name__ == "__main__":
    """
    Código de exemplo que demonstra o uso da biblioteca.
    
    Execute este arquivo diretamente para ver exemplos de uso:
        python rfid_tag_parser/tag_tid_parser.py
    """

    print("=" * 80)
    print("🏷️  RFID TAG TID PARSER - DEMONSTRAÇÃO")
    print("=" * 80)

    # TIDs de exemplo para demonstração
    example_tids = [
        "E2801190000000000000000A",  # Impinj Monza R6
        "E2801191000000000000000B",  # Impinj M730
        "E28011A0000000000000000C",  # Impinj M770
        "E2806915000000000000000E",  # NXP UCODE 9
        "FF00AA00000000000000002A",  # Fabricante desconhecido
    ]

    print("\n📋 Exemplos de Parsing de TID:")
    print("-" * 80)

    for i, tid in enumerate(example_tids, 1):
        try:
            print(f"\n{i}. TID: {tid}")

            # Usar a classe TagTidParser
            parser = TagTidParser(tid)

            print(f"   Fabricante: {parser.get_vendor_from_tid()}")
            print(f"   Modelo: {parser.get_tag_model_name()}")
            print(f"   Número do modelo: {parser.get_tag_model_number()}")
            print(f"   Serial (Hex): {parser.get_40bit_serial_hex()}")
            print(f"   Serial (Decimal): {parser.get_40bit_serial_decimal()}")
            print(f"   É Impinj: {parser._is_impinj_tid()}")
            print(f"   É NXP UCODE9: {parser._is_nxp_ucode9_tid()}")

            if parser._is_impinj_tid():
                print(f"   Monza Series ID: {parser.get_monza_series_id()}")

        except Exception as e:
            print(f"   ❌ Erro: {e}")

    print("\n" + "=" * 80)
    print("🚀 Exemplos de Funções de Conveniência:")
    print("=" * 80)

    # Demonstrar funções de conveniência
    test_tid = "E2801190123456789ABCDEF0"

    print(f"\nTID de teste: {test_tid}")
    print("-" * 50)

    try:
        # Parsing completo
        info = parse_tid(test_tid)
        print("✓ Parsing completo:")
        for key, value in info.items():
            print(f"   {key}: {value}")

        # Extração específica
        print("\n✓ Extração específica:")
        print(f"   Serial (hex): {get_serial_from_tid(test_tid, 'hex')}")
        print(f"   Serial (decimal): {get_serial_from_tid(test_tid, 'decimal')}")
        print(f"   Fabricante: {get_vendor_from_tid(test_tid)}")
        print(f"   Modelo: {get_model_from_tid(test_tid)}")

        # Validação
        print("\n✓ Validação:")
        print(f"   TID válido: {validate_tid(test_tid)}")
        print(f"   TID inválido: {validate_tid('INVALID')}")

    except Exception as e:
        print(f"❌ Erro na demonstração: {e}")

    print("\n" + "=" * 80)
    print("📚 Para mais exemplos, consulte:")
    print("   - examples/basic_usage.py")
    print("   - examples/batch_processing.py")
    print("   - examples/integration_example.py")
    print("   - docs/API.md")
    print("=" * 80)
