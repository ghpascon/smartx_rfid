from smartx_rfid.db import DatabaseManager
import logging
import re
from datetime import datetime
from copy import deepcopy

ID_BASE_URL = "db2+pyodbc:///?odbc_connect=DRIVER%3D%7BiSeries+Access+ODBC+Driver%7D%3BSYSTEM%3D172.19.0.22%3BUID%3D{user}%3BPWD%3D{password}%3BDefaultLibraries%3DAPPHEM%3B"


class IdLogisticClient:
    def __init__(self, url: str | None = None, user: str | None = None, password: str | None = None):
        self.url = url or ID_BASE_URL
        self.user = user
        self.password = password
        self.db_manager: DatabaseManager | None = None
        if self.is_logged_in():
            self.setup_db()

    def is_logged_in(self) -> bool:
        return self.user is not None and self.password is not None

    def setup_db(self):
        logging.info("Setting up AS400 database connection...")
        try:
            if self.url is None or self.user is None or self.password is None:
                logging.warning("AS400_URL or database credentials are not set. Skipping AS400 database setup.")
                logging.warning(
                    f"Current settings - AS400_URL: {self.url}, DB_USER: {self.user}, DB_PASSWORD: {self.password}"
                )
                return False, "Credenciais ou URL do AS400 não configurados."

            db_url = self.url.format(user=self.user, password=self.password)
            logging.info(f"Initializing AS400 DatabaseManager with URL: {db_url}")

            # First try: pass a driver-level timeout (some DBs accept this)
            try:
                self.db_manager = DatabaseManager(
                    database_url=db_url,
                    echo=True,
                    pool_size=5,
                    pool_timeout=10,
                    connect_args={"timeout": 10},
                    isolation_level="AUTOCOMMIT",
                )
                self.db_manager.initialize()

                # Quick verification to ensure the connect_args didn't break the driver
                try:
                    self.db_manager.execute_query("select 1 from sysibm.sysdummy1")
                    logging.info("AS400 test query succeeded (advanced settings)")
                except Exception as e:
                    logging.info(f"Advanced settings test query failed: {e}; falling back")
                    try:
                        self.db_manager.close()
                    except Exception:
                        pass
                    raise

            except Exception as e:
                logging.info(f"Failed to initialize DatabaseManager with advanced settings: {e}")

                # Fallback: try a minimal DatabaseManager using only the URL
                try:
                    self.db_manager = DatabaseManager(database_url=db_url)
                    self.db_manager.initialize()
                    try:
                        self.db_manager.execute_query("select 1")
                        logging.info("AS400 test query succeeded (simple settings)")
                    except Exception:
                        logging.exception(
                            "AS400 test query failed with simple settings; verify AS400_URL, ODBC driver and DB status"
                        )
                        return False, "Falha ao conectar, verifique URL e Credenciais do AS400."
                except Exception as e2:
                    logging.exception(f"Failed to initialize DatabaseManager with simple settings: {e2}")
                    return False, "Falha ao conectar, verifique URL e Credenciais do AS400."

            logging.info("AS400 database connection established.")
            return True, "Conexão com AS400 estabelecida com sucesso."

        except Exception as e:
            logging.error(f"Error setting up AS400 database: {e}")
            return False, str(e)

    def ensure_db(self):
        if self.db_manager is None:
            success, data = self.setup_db()
            if not success:
                logging.error(f"AS400 database is not set up: {data}")
                return False
        return True

    # POSITIONS
    def get_positions_by_user(self, user: str | None = None):
        user = user or self.user
        if not self.ensure_db():
            return False, "AS400 database is not available."
        try:
            query = (
                "SELECT numinv, datinv, libivt, motmvt, etadoc, codrsi1, numdoc, seqdoc, "
                "posicao_com_chave, posicao_sem_chave, posicao "
                "FROM viewposinv WHERE TRIM(UPPER(codrsi1)) = UPPER(:user) ORDER BY posicao"
            )
            result = self.db_manager.execute_query(query, {"user": user})
            return True, {
                row.get("posicao_com_chave"): {k: v.strip() if isinstance(v, str) else v for k, v in row.items()}
                for row in result
            }
        except Exception as e:
            logging.error(f"{e}")
            return False, str(e)

    def get_eans_on_support(self, support: str):
        if not self.ensure_db():
            return False, "AS400 database is not available."
        try:
            query = (
                f"SELECT ean, codpro, ds1pro, qtd_total FROM viewestoq "
                f"WHERE posicao_com_chave = '{support}' and qtd_total>0"
            )
            result = self.db_manager.execute_query(query)
            return True, [
                {k: v.strip() if isinstance(v, str) else int(v) if isinstance(v, float) else v for k, v in row.items()}
                for row in result
            ] if result else result
        except Exception as e:
            logging.error(f"{e}")
            return False, str(e)

    def save_position(
        self,
        position_info: dict,
        comparison: list,
    ):
        """
        Finish the inventory position by inserting the comparison results into the database.

        Args:
            position_info (dict): Information about the current position.
            comparison (list): List of comparison results between expected and read tags.

        Example:
            position_info = {
                'numinv': '123',
                'numdoc': '456',
                'seqdoc': '1',
                'etadoc': '2024-06-01',
                'posicao': 'A1'
            }
            comparison = [
                {'ean': '789', 'sku': 'SKU123', 'descricao': 'Product 1', 'exp_qty': 10, 'read_qty': 8, 'match': '!'},
                {'ean': '101', 'sku': 'SKU456', 'descricao': 'Product 2', 'exp_qty': 5, 'read_qty': 5, 'match': '='}
            ]
            save_position(position_info, comparison)
        """
        if not self.ensure_db():
            return False, "AS400 database is not available."
        try:
            if not position_info:
                return False, "No position details available for current support."

            query = (
                "INSERT INTO baseinv (numinv, numdoc, seqdoc, etadoc, codpro, pecas_esp, pecas_inv, status, posicao, user) "
                "VALUES (:numinv, :numdoc, :seqdoc, :etadoc, :codpro, :pecas_esp, :pecas_inv, :status, :posicao, :user)"
            )

            for row in comparison:
                is_unexpected = row.get("match") == "!"
                codpro = row["ean"] if is_unexpected else row.get("sku")
                params = {
                    "numinv": position_info.get("numinv"),
                    "numdoc": position_info.get("numdoc"),
                    "seqdoc": position_info.get("seqdoc"),
                    "etadoc": position_info.get("etadoc"),
                    "codpro": codpro,
                    "pecas_esp": row.get("exp_qty", row.get("expected_qty", 0)),
                    "pecas_inv": row.get("read_qty", row.get("current_qty", 0)),
                    "status": row.get("match"),
                    "posicao": position_info.get("posicao"),
                    "user": self.user,
                }
                self.db_manager.execute_query(query, params)
                logging.info(
                    f'Inserted baseinv for {codpro=} {position_info.get("posicao")=} {params["pecas_inv"]=} {params["status"]=}'
                )

            return True, None
        except Exception as e:
            logging.error(f"{e}")
            return False, str(e)

    # SUPPORT
    def get_data_supconf(self, value: str, field: str = "suporte"):
        if not self.ensure_db():
            return False, "AS400 database is not available."
        try:
            query = (
                f"SELECT pedido, suporte, sku, descricao, ean, quantidade, posicao FROM supconf WHERE {field} = :value"
            )
            params = {"value": value}
            result = self.db_manager.execute_query(query, params)
            return True, result
        except Exception as e:
            logging.error(f"{e}")
            return False, str(e)

    def get_logconf_status_count(self, days: int | None = None):
        if not self.ensure_db():
            return False, "AS400 database is not available."

        try:
            if days is None:
                query = (
                    "SELECT sinal, COUNT(*) AS count "
                    "FROM ("
                    "    SELECT sinal "
                    "    FROM logconf "
                    "    UNION ALL "
                    "    SELECT sinal "
                    "    FROM logconfdiv "
                    ") AS sinais "
                    "GROUP BY sinal "
                    "ORDER BY sinal"
                )
                result = self.db_manager.execute_query(query)
            else:
                query = (
                    "SELECT sinal, COUNT(*) AS count "
                    "FROM ("
                    "    SELECT sinal "
                    "    FROM logconf "
                    "    WHERE data >= CURDATE() - INTERVAL :days - 1 DAY "
                    "    UNION ALL "
                    "    SELECT sinal "
                    "    FROM logconfdiv "
                    "    WHERE data >= CURDATE() - INTERVAL :days - 1 DAY "
                    ") AS sinais "
                    "GROUP BY sinal "
                    "ORDER BY sinal"
                )

                params = {"days": days}
                result = self.db_manager.execute_query(query, params)
            data = {}
            for r in result:
                data[r["sinal"]] = r["count"]
            return True, data

        except Exception as e:
            logging.error(f"{e}")
            return False, str(e)

    def save_logconf(self, data: dict | list, tablename: str = "logconf"):
        """
        Save logconf data to the specified table.

        Args:
            tablename (str): The name of the table to save data to.
            data (dict|list): The data to save. Can be a single dictionary or a list of dictionaries.

        Returns:
            tuple: A tuple containing a boolean indicating success and a message or result.

        Example:
            save_logconf({
                'suporte': 'A1',
                'status': 'OK',
                'codpro': '12345',
                'quantidade': 10,
                'sinal': '=',
                'qtesperada': 10
            })
        """
        if not self.ensure_db():
            return False, "AS400 database is not available."
        if not isinstance(data, list):
            data = [data]

        if not data:
            return False, "No data to save."

        timestamp = datetime.now().astimezone()
        day, hora = timestamp.date().isoformat(), timestamp.time().isoformat()

        columns = [
            "suporte",
            "bancada",
            "data",
            "hora",
            "usuario",
            "embalagem",
            "status",
            "codpro",
            "quantidade",
            "sinal",
        ]
        if tablename.endswith("div"):
            columns.append("qtesperada")

        cols_str = ", ".join(columns)
        placeholders = ", ".join(":" + col for col in columns)
        query = f"INSERT INTO {tablename} ({cols_str}) VALUES ({placeholders})"

        params_list = []
        for d in data:
            row = {
                "suporte": d.get("suporte", d.get("posicao")),
                "bancada": d.get("bancada", 1),
                "data": day,
                "hora": hora,
                "usuario": self.user,
                "embalagem": d.get("embalagem", "HEM"),
                "status": d.get("status"),
                "codpro": d.get("codpro"),
                "quantidade": d.get("quantidade", d.get("current_qty", 0)),
                "sinal": d.get("sinal"),
            }
            if row["suporte"]:
                row["suporte"] = str(row["suporte"])
            if tablename.endswith("div"):
                row["qtesperada"] = d.get("qtesperada", d.get("expected_qty", 0))

            params_list.append(row)

        try:
            # execute_query accepts a list of mappings for executemany
            self.db_manager.execute_query(query, params_list)
            return True, None
        except Exception as e:
            logging.error(f"{e}")
            return False, str(e)

    # COMPARE
    @staticmethod
    def get_gtins_from_string(gtin_string: str):
        """
        Extract GTINs from a string.

        Args:
            gtin_string (str): A string containing GTINs separated by semicolons or commas,
                or a single GTIN string.

        Returns:
            list: A list of GTINs extracted from the string (strings, stripped).
        """
        if gtin_string is None:
            return []
        # Accept numeric values too
        if not isinstance(gtin_string, str):
            return [str(gtin_string)]

        parts = [p.strip() for p in re.split(r"[;,]", gtin_string) if p.strip()]
        return parts if parts else [gtin_string.strip()]

    @staticmethod
    def compare_gtins(expected_gtins: dict, current_gtins: dict):
        """
        Compare expected GTIN quantities with current GTIN quantities.

        Args:
            expected_gtins (dict): A dictionary of expected GTINs and their quantities.
            current_gtins (dict): A dictionary of current GTINs and their quantities.

        Returns:
            list: A list of dictionaries containing the comparison results for each GTIN.
        """
        data = []

        def _pop_mapping_value(mapping: dict, key: str) -> int:
            # try several key forms, prefer string keys
            if key in mapping:
                return mapping.pop(key)
            kstr = str(key).strip()
            if kstr in mapping:
                return mapping.pop(kstr)
            # try numeric form if applicable
            try:
                knum = int(float(kstr))
                if knum in mapping:
                    return mapping.pop(knum)
            except Exception:
                pass
            return 0

        for expected, qty in expected_gtins.items():
            # expected can be a single GTIN or multiple separated by ; or ,
            expected_keys = IdLogisticClient.get_gtins_from_string(expected)
            current_qty = 0
            for k in expected_keys:
                current_qty += _pop_mapping_value(current_gtins, k)

            status, sinal = ("SOB", ">") if current_qty > qty else ("FAL", "<") if current_qty < qty else ("OK", "=")

            data.append(
                {"gtin": expected, "expected_qty": qty, "current_qty": current_qty, "status": status, "sinal": sinal}
            )

        # remaining items in current_gtins are unexpected
        for current, qty in list(current_gtins.items()):
            data.append({"gtin": current, "expected_qty": 0, "current_qty": qty, "status": "INV", "sinal": "!"})

        return data

    @staticmethod
    def compare_gtins_support_data(support_data: list, current_gtins: dict):
        """
        Compare expected GTIN quantities on a support with current GTIN quantities.

        Args:
            support_data (list): A list of dictionaries from self.get_eans_on_support() or self.get_data_supconf().
            current_gtins (dict): A dictionary of current GTINs and their quantities.

        Returns:
            list: A list of dictionaries containing the comparison results for each GTIN.
        """
        data = deepcopy(support_data)

        def _pop_mapping_value(mapping: dict, key: str) -> int:
            if key in mapping:
                return mapping.pop(key)
            kstr = str(key).strip()
            if kstr in mapping:
                return mapping.pop(kstr)
            try:
                knum = int(float(kstr))
                if knum in mapping:
                    return mapping.pop(knum)
            except Exception:
                pass
            return 0

        for item in data:
            raw_gtin = item.get("ean")
            gtin_keys = IdLogisticClient.get_gtins_from_string(raw_gtin) if raw_gtin is not None else []
            current_qty = 0
            # sum and pop all GTIN keys that match
            for g in gtin_keys:
                current_qty += _pop_mapping_value(current_gtins, g)

            expected_qty = item.get("quantidade", item.get("qtd_total", 0))
            item["current_qty"] = current_qty
            item["expected_qty"] = expected_qty
            item["status"], item["sinal"] = (
                ("SOB", ">")
                if current_qty > expected_qty
                else ("FAL", "<")
                if current_qty < expected_qty
                else ("OK", "=")
            )

        keys = list(data[0].keys()) if data else []
        # remaining current_gtins are unexpected; add them
        for gtin, qty in list(current_gtins.items()):
            info = {key: None for key in keys}
            info.update({"ean": gtin, "current_qty": qty, "expected_qty": 0, "status": "INV", "sinal": "!"})
            if "ds1pro" in info:
                info["ds1pro"] = "NAO_ESPERADO"
            if "descricao" in info:
                info["descricao"] = "NAO_ESPERADO"
            data.append(info)

        return data
